import os
import asyncio
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

# CONFIG
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

scheduler = AsyncIOScheduler(timezone="Africa/Abidjan")

# --- RAPPELS AUTO ---
async def send_reminder(app: Application, chat_id: int, message: str):
    await app.bot.send_message(chat_id=chat_id, text=message)

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

def extraire_programme_complet(texte):
    # Lit ton tableau et sort: [(date, [nom1, nom2, nom3]),...]
    programme = []
    lignes = texte.split('\n')
    for ligne in lignes:
        # Cherche: 05/07/26 BERENICE NANCY MME DIBY
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
        "Envoie-moi la photo du programme du mois.\n"
        "Je vais programmer auto:\n"
        "1. Vendredi 18h : Rappel répétition + noms\n"
        "2. Samedi 14h : Rappel répétition 16h + noms"
    )

async def handle_programme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    texte_programme = ""
    
    if update.message.document:
        file = await update.message.document.get_file()
        file_bytes = await file.download_as_bytearray()
        texte_programme = lire_pdf(file_bytes)
        await update.message.reply_text("📄 PDF reçu. Je lis...")
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
        file_bytes = await file.download_as_bytearray()
        texte_programme = lire_photo(file_bytes)
        await update.message.reply_text("🖼️ Photo reçue. Je lis le programme...")
    else:
        await update.message.reply_text("Envoie une photo ou un PDF du programme stp")
        return
    
    programme = extraire_programme_complet(texte_programme)
    
    if not programme:
        await update.message.reply_text("Je n'ai pas pu lire les noms. Envoie une photo plus nette stp.")
        return

    await update.message.reply_text(f"✅ Programme lu! J'ai trouvé {len(programme)} dimanches.\nJe programme les rappels maintenant...")

    for date_str, noms in programme:
        try:
            # Convertir 05/07/26 en datetime
            dt_dimanche = datetime.strptime(date_str, "%d/%m/%y")
            dt_vendredi = dt_dimanche - timedelta(days=2)
            dt_samedi = dt_dimanche - timedelta(days=1)
            
            noms_str = f"AD: {noms[0]}\nCE: {noms[1]}\nOFF: {noms[2]}"

            # RAPPEL VENDREDI 18H
            scheduler.add_job(send_reminder, trigger=DateTrigger(run_date=dt_vendredi.replace(hour=18, minute=0)),
            args=[context.application, chat_id, f"🔔 RAPPEL: Répétition demain Samedi à 16h.\n\nPersonnes au programme Dimanche {date_str}:\n{noms_str}"],
            id=f"rappel_v_{chat_id}_{date_str}", replace_existing=True)

            # RAPPEL SAMEDI 14H
            scheduler.add_job(send_reminder, trigger=DateTrigger(run_date=dt_samedi.replace(hour=14, minute=0)),
            args=[context.application, chat_id, f"🔔 RAPPEL: Répétition AUJOURD'HUI à 16h.\n\nN'oubliez pas:\n{noms_str}\nVous intervenez demain Dimanche."],
            id=f"rappel_s_{chat_id}_{date_str}", replace_existing=True)
        except Exception as e:
            print(f"Erreur date {date_str}: {e}")

    await update.message.reply_text("Tous les rappels sont programmés ✅")

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.PDF, handle_programme))

    # ON LANCE LE SCHEDULER DANS LA BOUCLE DU BOT
    async def post_init(application: Application) -> None:
        scheduler.start()
        print("Scheduler démarré ✅")

    app.post_init = post_init
    
    print("Bot démarré...")
    app.run_polling()

if __name__ == '__main__':
    main()
