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

# --- RAPPELS AUTO AVEC CONFIRMATION EN PV ---
async def send_reminder(app: Application, chat_id: int, message: str):
    try:
        # 1. Envoie le vrai rappel dans le groupe
        await app.bot.send_message(chat_id=int(chat_id), text=message)

        # 2. Envoie la confirmation en PV à la personne qui a configuré le groupe
        user_id = None
        try:
            res = supabase.table("config_bot").select("user_id").eq("group_id", str(chat_id)).single().execute()
            if res.data:
                user_id = res.data['user_id']
        except Exception as e:
            logging.error(f"Erreur recherche user_id: {e}")

        if user_id:
            premiere_ligne = message.split('\n')[0]
            await app.bot.send_message(chat_id=int(user_id), text=f"✅ RAPPEL ENVOYÉ AU GROUPE\n{premiere_ligne}")

        logging.info(f"Rappel envoyé au groupe {chat_id}")
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
    user_id = update.message.from_user.id
    try:
        res = supabase.table("config_bot").select("group_id").eq("user_id", user_id).single().execute()
        if res.data and res.data.get('group_id'):
            await update.message.reply_text("Salut! Ton groupe est déjà configuré 🙌\n\nCommandes: /liste pour voir les rappels\nEnvoie-moi la photo ou le PDF du programme.")
            return
    except: pass

    await update.message.reply_text(
        "Salut! Je suis H-Bot V4.2.1 🤖\n\n"
        "ETAPE 1: Va dans ton groupe et tape /getid\n"
        "ETAPE 2: Copie l'ID ici en PV\n"
        "ETAPE 3: Envoie-moi la photo ou le PDF du programme"
    )
    context.user_data['attente_id'] = True

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    chat_title = update.message.chat.title if update.message.chat.title else "PV"
    await update.message.reply_text(f"✅ ID du groupe: `{chat_id}`\nNom: {chat_title}\n\nCopie cet ID et envoie-le-moi en privé.")

async def liste_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = scheduler.get_jobs()
    if not jobs:
        await update.message.reply_text("❌ Aucun rappel programmé pour l'instant.")
        return

    jours_fr = {"Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi", "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"}
    texte = "📅 *RAPPELS & NOMS PROGRAMMÉS:*\n\n"

    for job in sorted(jobs, key=lambda x: x.next_run_time):
        jour_en = job.next_run_time.strftime("%A")
        jour_fr = jours_fr.get(jour_en, jour_en)
        heure_str = job.next_run_time.strftime("%d/%m/%Y à %Hh%M")
        run_date = f"{jour_fr} {heure_str}"
        details = job.args[2] 
        texte += f"• *{run_date}*\n{details}\n\n"

    await update.message.reply_text(texte, parse_mode='Markdown')

async def handle_text_pv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('attente_id'):
        groupe_id = update.message.text.strip()
        user_id = update.message.from_user.id
        try:
            supabase.table("config_bot").upsert({"user_id": user_id, "group_id": str(groupe_id)}).execute()
            context.user_data['attente_id'] = False
            await update.message.reply_text("✅ Groupe enregistré! \n\nMaintenant, envoie-moi la photo ou le PDF du programme.")
        except Exception as e:
            logging.error(f"Erreur set groupe: {e}")
            await update.message.reply_text(f"❌ Erreur lors de l'enregistrement : {e}")
    else:
        await update.message.reply_text("Tape /start pour recommencer ou /liste pour voir les rappels.")

async def handle_programme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        res = supabase.table("config_bot").select("group_id").eq("user_id", user_id).single().execute()
        if not res.data or not res.data.get('group_id'):
            await update.message.reply_text("❌ Tu dois d'abord configurer ton groupe en faisant /start en privé.")
            return
        groupe_id = res.data['group_id']
    except Exception as e:
        logging.error(f"Erreur lecture config: {e}")
        await update.message.reply_text("❌ Erreur. Refais /start en privé.")
        return

    await update.message.reply_text("⏳ Je lis le programme...")
    file = await (update.message.photo[-1].get_file() if update.message.photo else update.message.document.get_file())
    file_bytes = await file.download_as_bytearray()
    texte = lire_photo(file_bytes) if update.message.photo else lire_pdf(file_bytes)

    programme = extraire_programme_complet(texte)
    if not programme:
        await update.message.reply_text("❌ Je n'ai pas pu lire. Vérifie le format de l'image ou du fichier.")
        return

    await update.message.reply_text(f"✅ {len(programme)} dimanches trouvés. Je programme les rappels...")

    for date_str, noms in programme:
        try:
            dt_dimanche = datetime.strptime(date_str, "%d/%m/%y")
            dt_vendredi = dt_dimanche - timedelta(days=2)
            dt_samedi = dt_dimanche - timedelta(days=1)
            noms_str = f"AD: {noms[0]}\nCE: {noms[1]}\nOFF: {noms[2]}"

            scheduler.add_job(send_reminder, DateTrigger(run_date=dt_vendredi.replace(hour=18, minute=0)),
                args=[context.application, groupe_id, f"🔔 RAPPEL GROUPE: Répétition demain Samedi à 16h.\n\nProgramme Dimanche {date_str}:\n{noms_str}"],
                id=f"v_{groupe_id}_{date_str}", replace_existing=True)

            scheduler.add_job(send_reminder, DateTrigger(run_date=dt_samedi.replace(hour=14, minute=0)),
                args=[context.application, groupe_id, f"🔔 RAPPEL: Répétition AUJOURD'HUI à 16h.\n\nN'oubliez pas:\n{noms_str}\nSoyez à l'heure!"],
                id=f"s_{groupe_id}_{date_str}", replace_existing=True)
        except ValueError:
            logging.error(f"Date invalide: {date_str}")

    await update.message.reply_text("✅ Tous les rappels sont programmés! Voici le récapitulatif détaillé :")
    await liste_commande(update, context)

async def post_init(application: Application) -> None:
    scheduler.start()
    logging.info("Scheduler démarré ✅")
    logging.info("Bot démarré et en ligne...")

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
