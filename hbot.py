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

# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- VARIABLES D'ENVIRONNEMENT ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Variables manquantes ! Vérifie TELEGRAM_TOKEN, SUPABASE_URL, SUPABASE_KEY sur Render.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# Tesseract : le chemin est généralement /usr/bin/tesseract sur Render
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
scheduler = AsyncIOScheduler(timezone="Africa/Abidjan")

# --- FONCTIONS ---
async def send_reminder(app: Application, chat_id: int, message: str):
    try:
        await app.bot.send_message(chat_id=int(chat_id), text=message)
        logging.info(f"Rappel envoyé au groupe {chat_id}")
    except Exception as e:
        logging.error(f"Erreur envoi rappel: {e}")

def lire_photo(file_bytes):
    image = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(image, lang='fra')

def lire_pdf(file_bytes):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in pdf_reader.pages:
        content = page.extract_text()
        if content:
            text += content + "\n"
    return text

def extraire_programme_complet(texte):
    programme = []
    lignes = [l.strip() for l in texte.split('\n') if l.strip()]
    for i, ligne in enumerate(lignes):
        date_match = re.search(r'(\d{2}/\d{2}/\d{2})', ligne)
        if date_match:
            date_str = date_match.group(1)
            reste = ligne.replace(date_str, '').strip()
            mots = [m for m in re.findall(r'[A-Za-zÀ-ÿ\'-]+', reste) if len(m) > 1]
            if len(mots) < 3 and i + 1 < len(lignes):
                suivante = lignes[i+1].strip()
                mots_suiv = re.findall(r'[A-Za-zÀ-ÿ\'-]+', suivante)
                mots.extend([m for m in mots_suiv if len(m) > 1])
            if len(mots) >= 3:
                programme.append((date_str, [mots[0], mots[1], mots[2]]))
    return programme

# --- COMMANDES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salut ! H-Bot est opérationnel. Tape /getid dans ton groupe et envoie-moi l'ID.")
    context.user_data['attente_id'] = True

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    await update.message.reply_text(f"✅ ID du groupe : `{chat_id}`")

async def liste_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = scheduler.get_jobs()
    if not jobs:
        await update.message.reply_text("❌ Aucun rappel.")
        return
    texte = "📅 *RAPPELS :*\n\n"
    for job in sorted(jobs, key=lambda x: x.next_run_time):
        heure_str = job.next_run_time.strftime("%d/%m/%Y à %Hh%M")
        texte += f"• *{heure_str}*\n{job.args[2]}\n\n"
    await update.message.reply_text(texte, parse_mode='Markdown')

async def handle_text_pv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('attente_id'):
        groupe_id = update.message.text.strip()
        user_id = update.message.from_user.id
        supabase.table("config_bot").upsert({"user_id": user_id, "group_id": str(groupe_id)}).execute()
        context.user_data['attente_id'] = False
        await update.message.reply_text("✅ Groupe enregistré !")
    else:
        await update.message.reply_text("Tape /start.")

async def handle_programme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    res = supabase.table("config_bot").select("group_id").eq("user_id", user_id).single().execute()
    if not res.data:
        await update.message.reply_text("❌ Fais /start d'abord.")
        return
    
    groupe_id = res.data['group_id']
    await update.message.reply_text("⏳ Lecture en cours...")
    
    file = await (update.message.photo[-1].get_file() if update.message.photo else update.message.document.get_file())
    file_bytes = await file.download_as_bytearray()
    texte = lire_photo(file_bytes) if update.message.photo else lire_pdf(file_bytes)
    
    programme = extraire_programme_complet(texte)
    for date_str, noms in programme:
        dt_dimanche = datetime.strptime(date_str, "%d/%m/%y")
        noms_str = f"Adoration: {noms[0]}\nCélébration: {noms[1]}\nOffrande: {noms[2]}"
        scheduler.add_job(send_reminder, DateTrigger(run_date=(dt_dimanche - timedelta(days=2)).replace(hour=18)),
            args=[context.application, groupe_id, f"🔔 RAPPEL SAMEDI 16H\n{noms_str}"], id=f"v_{date_str}", replace_existing=True)
    await update.message.reply_text("✅ Programmation terminée.")

async def post_init(application: Application) -> None:
    scheduler.start()
    logging.info("Bot démarré ✅")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('getid', get_id))
    app.add_handler(CommandHandler('liste', liste_commande))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_text_pv))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.PDF, handle_programme))
    app.post_init = post_init
    app.run_polling()

if __name__ == '__main__':
    main()
