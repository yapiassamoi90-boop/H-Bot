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

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
scheduler = AsyncIOScheduler(timezone="Africa/Abidjan")
JOURS_FR = {"Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi", "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"}

async def send_reminder(bot, chat_id: int, message: str):
    try:
        await bot.send_message(chat_id=int(chat_id), text=message)
        res = supabase.table("config_bot").select("user_id").eq("group_id", str(chat_id)).single().execute()
        if res.data: await bot.send_message(chat_id=int(res.data['user_id']), text=f"✅ Rappel envoyé au groupe")
    except Exception as e: logging.error(f"Erreur envoi: {e}")

def lire_photo(file_bytes: bytes) -> str: return pytesseract.image_to_string(Image.open(io.BytesIO(file_bytes)), lang='fra')
def lire_pdf(file_bytes: bytes) -> str: return "\n".join([page.extract_text() for page in PyPDF2.PdfReader(io.BytesIO(file_bytes)).pages if page.extract_text()])

def extraire_programme_complet(texte: str):
    programme = []
    lignes = [l.strip() for l in texte.split('\n') if l.strip()]
    for i, ligne in enumerate(lignes):
        if date_match := re.search(r'(\d{2}/\d{2}/\d{2,4})', ligne):
            date_str = date_match.group(1)
            reste = ligne.replace(date_str, '').strip()
            mots = [m.strip() for m in re.findall(r'[A-Za-zÀ-ÿ\'\. ]+', reste) if len(m.strip()) > 2]
            if len(mots) < 3 and i + 1 < len(lignes): mots.extend([m.strip() for m in re.findall(r'[A-Za-zÀ-ÿ\'\. ]+', lignes[i+1]) if len(m.strip()) > 2])
            if len(mots) >= 3: programme.append((date_str, [mots[0], mots[1], mots[2]]))
    return programme

def get_group_id(user_id: int):
    try: return supabase.table("config_bot").select("group_id").eq("user_id", user_id).single().execute().data['group_id']
    except: return None

# --- COMMANDES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = get_group_id(update.message.from_user.id)
    if group_id:
        await update.message.reply_text(f"👋 Re-salut!\nTon groupe est configuré: `{group_id}`\n\nBalance ton programme en Image/PDF", parse_mode='Markdown')
    else:
        await update.message.reply_text("👋 Salut!\n\n1. Va dans ton groupe et tape `/getid`\n2. Reviens ici et envoie-moi l'ID", parse_mode='Markdown')

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"✅ ID de ce chat: `{update.message.chat_id}`\n\nCopie ce nombre et envoie-le moi en PV.", parse_mode='Markdown')

async def liste_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = scheduler.get_jobs()
    if not jobs: await update.message.reply_text("❌ Aucun rappel programmé."); return
    texte = "📅 *RAPPELS PROGRAMMÉS:*\n\n"
    for job in sorted(jobs, key=lambda x: x.next_run_time):
        jour_fr = JOURS_FR.get(job.next_run_time.strftime("%A"))
        texte += f"• *{jour_fr} {job.next_run_time.strftime('%d/%m/%Y à %Hh%M')}*\n"
    await update.message.reply_text(texte, parse_mode='Markdown')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not get_group_id(update.message.from_user.id):
        if text.startswith('-100') and text[1:].isdigit():
            supabase.table("config_bot").upsert({"user_id": update.message.from_user.id, "group_id": text}, on_conflict='user_id').execute()
            await update.message.reply_text(f"✅ ID reçu: `{text}`\n\nParfait! Balance ton programme en Image/PDF", parse_mode='Markdown')
        else: await update.message.reply_text("❌ Ça ne ressemble pas à un ID.\nIl doit commencer par -100")
    else: await update.message.reply_text("Envoie une Image/PDF de programme ou fais /liste")

async def handle_programme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (group_id := get_group_id(update.message.from_user.id)):
        await update.message.reply_text("❌ Envoie-moi d'abord l'ID avec /start.");
        return
    await update.message.reply_text("⏳ Analyse OCR en cours...")
    try:
        file = await (update.message.photo[-1].get_file() if update.message.photo else update.message.document.get_file())
        texte = lire_photo(await file.download_as_bytearray()) if update.message.photo else lire_pdf(await file.download_as_bytearray())
        if not texte: await update.message.reply_text("⚠️ Texte illisible."); return
        programme = extraire_programme_complet(texte)
        if not programme: await update.message.reply_text("❌ Aucune date trouvée."); return
        for date_str, noms in programme:
            dt_dim = datetime.strptime(date_str, "%d/%m/%y") if len(date_str) == 8 else datetime.strptime(date_str, "%d/%m/%Y")
            noms_str = f"AD: {noms[0]}\nCE: {noms[1]}\nOFF: {noms[2]}"
            scheduler.add_job(send_reminder, DateTrigger(run_date=(dt_dim - timedelta(days=2)).replace(hour=18)), args=[context.bot, group_id, f"🔔 RAPPEL GROUPE: Répétition demain Samedi 16h\nProgramme Dim {date_str}:\n{noms_str}"], id=f"v_{group_id}_{date_str}", replace_existing=True)
            scheduler.add_job(send_reminder, DateTrigger(run_date=(dt_dim - timedelta(days=1)).replace(hour=14)), args=[context.bot, group_id, f"🔔 RAPPEL: Répétition AUJOURD'HUI 16h\nN'oubliez pas:\n{noms_str}"], id=f"s_{group_id}_{date_str}", replace_existing=True)
        await update.message.reply_text(f"✅ Succès! {len(programme)} programmes programmés."); await liste_commande(update, context)
    except Exception as e: await update.message.reply_text(f"❌ Erreur : {str(e)}")

async def post_init(application: Application) -> None: scheduler.start()

def main():
    app = Application.builder().token(TOKEN).build()
    app.post_init = post_init
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('getid', get_id)) # ON GARDE CELUI-LA
    app.add_handler(CommandHandler('liste', liste_commande))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.PDF, handle_programme))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)) # Pour recevoir l'ID
    app.run_polling()

if __name__ == '__main__': main()
