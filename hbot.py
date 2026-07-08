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

# --- FIX POUR TESSERACT DANS DOCKER ---
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

scheduler = AsyncIOScheduler(timezone="Africa/Abidjan")

# --- RAPPELS AUTO ---
async def send_reminder(app: Application, chat_id: int, message: str):
    await app.bot.send_message(chat_id=int(chat_id), text=message)

# --- LECTURE PDF/PHOTO ---
def lire_photo(file_bytes):
    image = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(image, lang='fra')
    return text

def lire_pdf(file_bytes):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in pdf_reader.pages:
        if page.extract_text():
            text += page.extract_text() + "\n"
    return text

def extraire_programme_complet(texte):
    programme = []
    lignes = texte.split('\n')
    for ligne in lignes:
        match = re.search(r'(\d{2}/\d{2}/\d{2})\s+([A-Z\s\']+)\s+([A-Z\s\']+)\s+([A-Z\s\']+)', ligne)
        if match:
            date_str = match.group(1)
            nom1 = match.group(2).strip()
            nom2 = match.group(3).strip()
            nom3 = match.group(4).strip()
            programme.append((date_str, [nom1, nom2, nom3]))
    return programme

# --- COMMANDES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salut! Je suis H-Bot 🙌\n\n"
        "ETAPE 1: Dans le groupe tape /getid pour avoir l'ID\n"
        "ETAPE 2: En PV tape /setgroupe ID_GROUPE\n"
        "ETAPE 3: Envoie-moi la photo du programme en PV"
    )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    chat_title = update.message.chat.title if update.message.chat.title else "PV"
    await update.message.reply_text(
        f"✅ ID du groupe: `{chat_id}`\n"
        f"Nom: {chat_title}\n\n"
        f"Copie cet ID et va en PV avec moi pour faire /setgroupe {chat_id}"
    )

async def set_groupe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        groupe_id = update.message.text.split()[1]
        user_id = update.message.from_user.id
        supabase.table("config_bot").upsert({"user_id": user_id, "groupe_id": groupe_id}).execute()
        await update.message.reply_text(f"✅ Groupe enregistré: {groupe_id}\n\nMaintenant envoie-moi la photo du programme ici en privé.")
    except:
        await update.message.reply_text("Utilise: /setgroupe -1001234567890")

async def handle_programme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    res = supabase.table("config_bot").select("groupe_id").eq("user_id", user_id).single().execute()
    if not res.data:
        await update.message.reply_text("D'abord fais /setgroupe ID_DU_GROUPE en privé")
        return
    groupe_id = res.data['groupe_id']

    texte_programme = ""
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        file_bytes = await file.download_as_bytearray()
        texte_programme = lire_photo(file_bytes)
        await update.message.reply_text("🖼️ Photo reçue. Je lis le programme...")
    elif update.message.document:
        file = await update.message.document.get_file()
        file_bytes = await file.download_as_bytearray()
        texte_programme = lire_pdf(file_bytes)
        await update.message.reply_text("📄 PDF reçu. Je lis le programme...")

    programme = extraire_programme_complet(texte_programme)

    if not programme:
        await update.message.reply_text("Je n'ai pas pu lire. Envoie une photo plus nette.")
        return

    await update.message.reply_text(f"✅ Programme lu! {len(programme)} dimanches trouvés.\nJ'envoie les rappels dans le groupe.")

    for date_str, noms in programme:
        # FIX ICI: %m pour mois
        dt_dimanche = datetime.strptime(date_str, "%d/%m/%y")
        dt_vendredi = dt_dimanche - timedelta(days=2)
        dt_samedi = dt_dimanche - timedelta(days=1)

        noms_str = f"AD: {noms[0]}\nCE: {noms[1]}\nOFF: {noms[2]}"

        scheduler.add_job(send_reminder, trigger=DateTrigger(run_date=dt_vendredi.replace(hour=18, minute=0)),
        args=[context.application, groupe_id, f"🔔 RAPPEL GROUPE: Répétition demain Samedi à 16h.\n\nPersonnes au programme Dimanche {date_str}:\n{noms_str}"],
        id=f"rappel_v_{groupe_id}_{date_str}", replace_existing=True)

        scheduler.add_job(send_reminder, trigger=DateTrigger(run_date=dt_samedi.replace(hour=14, minute=0)),
        args=[context.application, groupe_id, f"🔔 RAPPEL: Répétition AUJOURD'HUI à 16h.\n\nN'oubliez pas:\n{noms_str}\nSoyez à l'heure!"],
        id=f"rappel_s_{groupe_id}_{date_str}", replace_existing=True)

    await update.message.reply_text("Tous les rappels sont programmés dans le groupe ✅")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('getid', get_id))
    app.add_handler(CommandHandler('setgroupe', set_groupe))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.PDF, handle_programme))

    async def post_init(application: Application) -> None:
        scheduler.start()
        logging.info("Scheduler démarré ✅")
        logging.info("Bot démarré...")

    app.post_init = post_init
    app.run_polling()

if __name__ == '__main__':
    main()
