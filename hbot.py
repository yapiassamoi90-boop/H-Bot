import os
import asyncio
import logging
import pytesseract
from PIL import Image
import io
import re
from datetime import datetime, timedelta
from supabase import create_client, Client
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import PyPDF2

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- VARIABLES D'ENV ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Variable manquante! Vérifie TELEGRAM_TOKEN, SUPABASE_URL, SUPABASE_KEY sur Railway")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

scheduler = AsyncIOScheduler(timezone="Africa/Abidjan")

# --- RAPPELS AUTO ---
async def send_reminder(app: Application, chat_id: int, message: str):
    try:
        await app.bot.send_message(chat_id=int(chat_id), text=message)
    except Exception as e:
        logging.error(f"Erreur envoi rappel: {e}")

# --- LECTURE PDF/PHOTO ---
def lire_photo(file_bytes):
    image = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(image, lang='fra')

def lire_pdf(file_bytes):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in pdf_reader.pages:
        if page.extract_text():
            text += page.extract_text() + "\n"
    return text

def extraire_programme_complet(texte):
    programme = []
    pattern = r'(\d{2}/\d{2}/\d{2})\s+([A-ZÀ-ÿ\s\-\']+)\s+([A-ZÀ-ÿ\s\-\']+)\s+([A-ZÀ-ÿ\s\-\']+)'
    for ligne in texte.split('\n'):
        ligne = ligne.strip()
        match = re.search(pattern, ligne)
        if match:
            date_str, nom1, nom2, nom3 = match.groups()
            programme.append((date_str, [nom1.strip(), nom2.strip(), nom3.strip()]))
    return programme

# --- NOUVEAU PARCOURS INTERACTIF ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        res = supabase.table("config_bot").select("group_id").eq("user_id", user_id).single().execute()
        if res.data and res.data.get('group_id'):
            await update.message.reply_text("Salut ! Tu as déjà configuré ton groupe. Envoie-moi simplement la photo ou le PDF du programme.")
            return
    except: pass
    
    await update.message.reply_text("Salut ! Pour commencer, après avoir fait /getid dans ton groupe, donne-moi ici l'ID du groupe (ex: -100...)")
    context.user_data['attente_id'] = True

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"✅ ID du groupe: `{update.message.chat_id}`\nCopie cet ID et envoie-le-moi en privé après avoir tapé /start.")

async def handle_text_pv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('attente_id'):
        groupe_id = update.message.text.strip()
        user_id = update.message.from_user.id
        try:
            supabase.table("config_bot").upsert({"user_id": user_id, "group_id": str(groupe_id)}).execute()
            context.user_data['attente_id'] = False
            await update.message.reply_text("✅ ID enregistré ! Maintenant, envoie-moi la photo ou le PDF du programme.")
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur : {e}")
    else:
        await update.message.reply_text("Tape /start pour recommencer ou envoie-moi une photo.")

async def handle_programme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        res = supabase.table("config_bot").select("group_id").eq("user_id", user_id).single().execute()
        groupe_id = res.data['group_id']
    except:
        await update.message.reply_text("❌ Tu dois d'abord configurer ton groupe en faisant /start en privé.")
        return

    file = await (update.message.photo[-1].get_file() if update.message.photo else update.message.document.get_file())
    file_bytes = await file.download_as_bytearray()
    texte = lire_photo(file_bytes) if update.message.photo else lire_pdf(file_bytes)
    
    programme = extraire_programme_complet(texte)
    if not programme:
        await update.message.reply_text("Je n'ai pas pu lire le programme. Vérifie le format: DD/MM/YY NOM1 NOM2 NOM3")
        return

    await update.message.reply_text(f"✅ {len(programme)} dimanches trouvés. Rappels programmés !")
    for date_str, noms in programme:
        try:
            dt_dimanche = datetime.strptime(date_str, "%d/%m/%y")
            noms_str = f"AD: {noms[0]}\nCE: {noms[1]}\nOFF: {noms[2]}"
            scheduler.add_job(send_reminder, DateTrigger(run_date=(dt_dimanche - timedelta(days=2)).replace(hour=18)), args=[context.application, groupe_id, f"🔔 RAPPEL GROUPE: Répétition demain.\n\nProgramme Dimanche {date_str}:\n{noms_str}"], id=f"v_{groupe_id}_{date_str}", replace_existing=True)
            scheduler.add_job(send_reminder, DateTrigger(run_date=(dt_dimanche - timedelta(days=1)).replace(hour=14)), args=[context.application, groupe_id, f"🔔 RAPPEL: Répétition AUJOURD'HUI à 16h.\n\nN'oubliez pas:\n{noms_str}"], id=f"s_{groupe_id}_{date_str}", replace_existing=True)
        except: continue

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('getid', get_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_pv))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.PDF, handle_programme))
    app.post_init = lambda app: scheduler.start()
    app.run_polling()

if __name__ == '__main__':
    main()
