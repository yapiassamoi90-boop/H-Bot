import os
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

# Configuration des logs
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("❌ Variables d'environnement manquantes sur Render!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
scheduler = AsyncIOScheduler(timezone="Africa/Abidjan")
JOURS_FR = {"Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi", "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"}

# --- FONCTIONS ---
async def send_reminder(bot, chat_id: int, message: str):
    """Envoie le rappel au groupe et confirme en PV"""
    try:
        await bot.send_message(chat_id=int(chat_id), text=message)
        
        # Confirmation admin
        res = supabase.table("config_bot").select("user_id").eq("group_id", str(chat_id)).single().execute()
        if res.data:
            user_id = res.data['user_id']
            await bot.send_message(chat_id=int(user_id), text=f"✅ Rappel envoyé au groupe:\n{message.splitlines()[0]}")
    except Exception as e:
        logging.error(f"Erreur envoi rappel: {e}")

def lire_photo(file_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(image, lang='fra')

def lire_pdf(file_bytes: bytes) -> str:
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    return "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])

def extraire_programme_complet(texte: str):
    programme = []
    lignes = [l.strip() for l in texte.split('\n') if l.strip()]
    for i, ligne in enumerate(lignes):
        date_match = re.search(r'(\d{2}/\d{2}/\d{2,4})', ligne)
        if date_match:
            date_str = date_match.group(1)
            reste = ligne.replace(date_str, '').strip()
            mots = [m.strip() for m in re.findall(r'[A-Za-zÀ-ÿ\'\. ]+', reste) if len(m.strip()) > 2]
            if len(mots) < 3 and i + 1 < len(lignes):
                mots.extend([m.strip() for m in re.findall(r'[A-Za-zÀ-ÿ\'\. ]+', lignes[i+1]) if len(m.strip()) > 2])
            if len(mots) >= 3:
                programme.append((date_str, [mots[0], mots[1], mots[2]]))
    return programme

# --- COMMANDES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    res = supabase.table("config_bot").select("group_id").eq("user_id", user_id).single().execute()
    if res.data:
        await update.message.reply_text("Salut ! Tu es déjà configuré. Envoie-moi ton programme.")
        return
    await update.message.reply_text("Tape /getid dans ton groupe et envoie-moi l'ID ici.")
    context.user_data['attente_id'] = True

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"✅ ID du groupe: `{update.message.chat_id}`", parse_mode='Markdown')

async def handle_text_pv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('attente_id'):
        supabase.table("config_bot").upsert({"user_id": update.message.from_user.id, "group_id": update.message.text.strip()}).execute()
        context.user_data['attente_id'] = False
        await update.message.reply_text("✅ Groupe enregistré ! Envoie maintenant le programme (Image/PDF).")

async def handle_programme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    res = supabase.table("config_bot").select("group_id").eq("user_id", user_id).single().execute()
    if not res.data:
        await update.message.reply_text("❌ Configure ton groupe avec /start d'abord.")
        return
    
    groupe_id = res.data['group_id']
    await update.message.reply_text("⏳ Lecture du programme...")
    
    file = await (update.message.photo[-1].get_file() if update.message.photo else update.message.document.get_file())
    file_bytes = await file.download_as_bytearray()
    texte = lire_photo(file_bytes) if update.message.photo else lire_pdf(file_bytes)
    programme = extraire_programme_complet(texte)

    for date_str, noms in programme:
        try:
            dt_dim = datetime.strptime(date_str, "%d/%m/%y") if len(date_str) == 8 else datetime.strptime(date_str, "%d/%m/%Y")
            noms_str = f"AD: {noms[0]}\nCE: {noms[1]}\nOFF: {noms[2]}"
            # Programmation J-2 à 18h
            scheduler.add_job(send_reminder, DateTrigger(run_date=dt_dim - timedelta(days=2, hours=6)),
                args=[context.bot, groupe_id, f"🔔 RAPPEL:\n{noms_str}"], id=f"v_{groupe_id}_{date_str}", replace_existing=True)
        except Exception as e:
            logging.error(f"Erreur job: {e}")

    await update.message.reply_text(f"✅ {len(programme)} programmes programmés.")

def main():
    app = Application.builder().token(TOKEN).build()
    scheduler.start()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('getid', get_id))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, handle_text_pv))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.PDF, handle_programme))
    app.run_polling()

if __name__ == '__main__':
    main()
