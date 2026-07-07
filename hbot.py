import os
import asyncio
import threading
import pytesseract
from PIL import Image
import io
import re
from datetime import datetime, timedelta
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import PyPDF2

# CONFIGURATION
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# États de la conversation
ASK_NOM, ASK_DATE, ASK_CONTACT, ASK_PROGRAMME_TEXTE, ASK_PROGRAMME_PHOTO = range(5)

# Initialiser le scheduler
scheduler = AsyncIOScheduler(timezone="Africa/Abidjan")

# --- FONCTIONS RAPPELS ---
async def send_reminder(app: Application, chat_id: int, message: str):
    await app.bot.send_message(chat_id=chat_id, text=message)

def setup_weekly_reminders(app: Application, user_id: int, chat_id: int):
    scheduler.add_job(send_reminder, 'cron', day_of_week='fri', hour=18, minute=0, args=[app, chat_id, "🔔 Rappel: Envoie ton programme pour la semaine prochaine stp 🙏"], id=f"rappel_vendredi_{user_id}", replace_existing=True)
    scheduler.add_job(send_reminder, 'cron', day_of_week='sat', hour=14, minute=0, args=[app, chat_id, "⏰ Rappel: Programme pas encore reçu. Tu l'envoies quand?"], id=f"rappel_samedi14_{user_id}", replace_existing=True)
    scheduler.add_job(send_reminder, 'cron', day_of_week='sat', hour=16, minute=0, args=[app, chat_id, "🚨 Dernier rappel: Sans programme on ne peut pas chanter demain!"], id=f"rappel_samedi16_{user_id}", replace_existing=True)

# --- LECTURE PDF ET PHOTO ---
def lire_pdf(file_bytes):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

def lire_photo(file_bytes):
    image = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(image, lang='fra')
    return text

def extraire_programme(texte):
    # Cherche les lignes avec Jour Heure
    lignes = []
    pattern = r"(Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi|Dimanche).*?(\d{1,2}h\d{0,2})"
    matches = re.findall(pattern, texte, re.IGNORECASE)
    for match in matches:
        lignes.append(f"{match[0]} {match[1]}")
    return lignes if lignes else [texte[:200]]

# --- COMMANDES BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salut! Je suis H-Bot 🙌\nEnvoie /register pour commencer")
    return ASK_NOM

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("C'est quoi ton nom?")
    return ASK_NOM

async def ask_nom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nom'] = update.message.text
    await update.message.reply_text("Ta date de naissance? JJ/MM/AAAA")
    return ASK_DATE

async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['date'] = update.message.text
    await update.message.reply_text("Ton numéro de contact?")
    return ASK_CONTACT

async def ask_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    nom = context.user_data['nom']
    date = context.user_data['date']
    contact = update.message.text
    
    supabase.table("programme").insert({"user_id": user_id, "nom": nom, "date_naissance": date, "contact": contact}).execute()
    
    setup_weekly_reminders(context.application, user_id, chat_id)
    
    await update.message.reply_text(f"Merci {nom} ✅\nTu recevras 3 rappels auto chaque semaine.\n\nEnvoie maintenant ton programme: en texte, PDF ou Photo")
    return ASK_PROGRAMME_TEXTE

async def handle_programme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    texte_programme = ""
    
    if update.message.text:
        texte_programme = update.message.text
    elif update.message.document:
        file = await update.message.document.get_file()
        file_bytes = await file.download_as_bytearray()
        texte_programme = lire_pdf(file_bytes)
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
        file_bytes = await file.download_as_bytearray()
        texte_programme = lire_photo(file_bytes)
    
    programmes = extraire_programme(texte_programme)
    
    for prog in programmes:
        supabase.table("programme").insert({"user_id": user_id, "programme": prog}).execute()
    
    await update.message.reply_text(f"Programme reçu ✅\nJ'ai trouvé {len(programmes)} répétition(s).\nJe vais te rappeler automatiquement.")
    return ASK_PROGRAMME_TEXTE

def main():
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), CommandHandler('register', register)],
        states={
            ASK_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_nom)],
            ASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_date)],
            ASK_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_contact)],
            ASK_PROGRAMME_TEXTE: [MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.PDF, handle_programme)],
        },
        fallbacks=[]
    )
    
    app.add_handler(conv_handler)
    scheduler.start()
    app.run_polling()

if __name__ == '__main__':
    main()
