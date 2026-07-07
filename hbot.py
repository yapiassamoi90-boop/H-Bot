import os
import asyncio
import pytesseract
from PIL import Image
import io
import re
from datetime import datetime
from supabase import create_client, Client
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import PyPDF2

# CONFIG
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ASK_NOM, ASK_DATE, ASK_CONTACT, ASK_PROGRAMME = range(4)
scheduler = AsyncIOScheduler(timezone="Africa/Abidjan")

# --- RAPPELS AUTO ---
async def send_reminder(app: Application, chat_id: int, message: str):
    await app.bot.send_message(chat_id=chat_id, text=message)

def setup_weekly_reminders(app: Application, user_id: int, chat_id: int):
    scheduler.add_job(send_reminder, 'cron', day_of_week='fri', hour=18, minute=0, args=[app, chat_id, "🔔 Rappel: Envoie ton programme pour la semaine prochaine stp 🙏"], id=f"rappel_vendredi_{user_id}", replace_existing=True)
    scheduler.add_job(send_reminder, 'cron', day_of_week='sat', hour=14, minute=0, args=[app, chat_id, "⏰ Rappel: Programme pas encore reçu. Tu l'envoies quand?"], id=f"rappel_samedi14_{user_id}", replace_existing=True)
    scheduler.add_job(send_reminder, 'cron', day_of_week='sat', hour=16, minute=0, args=[app, chat_id, "🚨 Dernier rappel: Sans programme on ne peut pas chanter demain!"], id=f"rappel_samedi16_{user_id}", replace_existing=True)

# --- LECTURE PDF/PHOTO ---
def lire_pdf(file_bytes):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n"
    return text

def lire_photo(file_bytes):
    image = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(image, lang='fra')
    return text

def extraire_programme(texte):
    pattern = r"(Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi|Dimanche).*?(\d{1,2}h\d{0,2})"
    matches = re.findall(pattern, texte, re.IGNORECASE)
    if matches:
        return [f"{m[0]} à {m[1]}" for m in matches]
    return [texte[:300]]

# --- COMMANDES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salut! Je suis H-Bot 🙌\nTape /register pour commencer")
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
    context.user_data['contact'] = update.message.text
    
    supabase.table("programme").insert({"user_id": user_id, "nom": context.user_data['nom'], "date_naissance": context.user_data['date'], "contact": context.user_data['contact']}).execute()
    
    setup_weekly_reminders(context.application, user_id, chat_id)
    
    await update.message.reply_text(f"Merci {context.user_data['nom']} ✅\nTu recevras 3 rappels auto.\n\nEnvoie maintenant ton programme: en texte, PDF ou Photo")
    return ASK_PROGRAMME

async def handle_programme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    texte_programme = ""
    
    if update.message.text:
        texte_programme = update.message.text
    elif update.message.document:
        file = await update.message.document.get_file()
        file_bytes = await file.download_as_bytearray()
        texte_programme = lire_pdf(file_bytes)
        await update.message.reply_text("📄 PDF reçu. Je lis...")
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
        file_bytes = await file.download_as_bytearray()
        texte_programme = lire_photo(file_bytes)
        await update.message.reply_text("🖼️ Photo reçue. Je lis...")
    
    programmes = extraire_programme(texte_programme)
    
    for prog in programmes:
        supabase.table("programme").insert({"user_id": user_id, "programme": prog}).execute()
    
    await update.message.reply_text(f"Programme reçu ✅\nJ'ai trouvé: \n" + "\n".join(programmes) + "\n\nJe vais te rappeler automatiquement.")
    return ASK_PROGRAMME

def main():
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), CommandHandler('register', register)],
        states={
            ASK_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_nom)],
            ASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_date)],
            ASK_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_contact)],
            ASK_PROGRAMME: [MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.PDF, handle_programme)],
        },
        fallbacks=[]
    )
    
    app.add_handler(conv_handler)
    scheduler.start()
    print("Bot démarré...")
    app.run_polling()

if __name__ == '__main__':
    main()
