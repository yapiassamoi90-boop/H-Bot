import os
import threading
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes, MessageHandler, 
                          filters, ConversationHandler)
from supabase import create_client, Client
from flask import Flask

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TZ = pytz.timezone("Africa/Abidjan")

# Étapes de la conversation
ID, JOUR, HEURE, CHANTRE, TYPE, URL, TEXTE, DATE = range(8)

# --- FLASK (POUR RAILWAY) ---
app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "H-BOT V3 opérationnel chef 💚"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app_flask.run(host='0.0.0.0', port=port)

# --- LOGIQUE DE SCAN ROBUSTE ---
async def scan_et_envoyer(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(TZ)
    today_date = now.strftime("%d/%m/%Y")
    heure_actuelle = now.strftime("%H:%M")
    jour_actuel = now.strftime("%A") 
    
    response = supabase.table("programmes").select("*").eq("actif", True).execute()
    for p in response.data:
        # Nettoyage : coupe les secondes pour comparer HH:MM
        db_heure = str(p['heure'])
        if ":" in db_heure:
            db_heure = ":".join(db_heure.split(":")[:2])
        
        if db_heure == heure_actuelle:
            match_date = (p['date_complete'] == today_date)
            match_jour = (p['jour'] == jour_actuel)
            
            if match_date or match_jour:
                msg = f"🔔 PROGRAMME: {p['chantre']}\n\n{p['texte']}"
                try:
                    if p['type_media'] == "image": await context.bot.send_photo(p['chat_id'], photo=p['url_media'], caption=msg)
                    elif p['type_media'] == "video": await context.bot.send_video(p['chat_id'], video=p['url_media'], caption=msg)
                    elif p['type_media'] == "vocal": await context.bot.send_voice(p['chat_id'], voice=p['url_media'], caption=msg)
                    else: await context.bot.send_message(p['chat_id'], text=msg)
                    
                    if p['date_complete']:
                        supabase.table("programmes").update({"actif": False}).eq("id", p['id']).execute()
                except Exception as e: print(f"Erreur envoi: {e}")

# --- HANDLERS CONVERSATION ---
async def start_ajouter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Quel est l'ID du groupe ? (/get_id dans le groupe pour le savoir)")
    return ID

async def get_id_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.message.text
    await update.message.reply_text("Jour ? (ex: Sunday, Monday...)")
    return JOUR

async def get_jour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['jour'] = update.message.text
    await update.message.reply_text("Heure ? (format HH:MM)")
    return HEURE

async def get_heure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['heure'] = update.message.text
    await update.message.reply_text("Chantre / Titre ?")
    return CHANTRE

async def get_chantre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chantre'] = update.message.text
    await update.message.reply_text("Type de média ? (image, video, vocal, ou tape skip)")
    return TYPE

async def get_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == 'skip':
        context.user_data['type'] = 'texte'
        context.user_data['url'] = 'none'
        await update.message.reply_text("Texte du message :")
        return TEXTE
    context.user_data['type'] = update.message.text
    await update.message.reply_text("Lien URL du média (ou tape skip) :")
    return URL

async def get_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['url'] = 'none' if update.message.text.lower() == 'skip' else update.message.text
    await update.message.reply_text("Texte du message :")
    return TEXTE

async def get_texte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['texte'] = update.message.text
    await update.message.reply_text("Date précise (JJ/MM/AAAA) ? Sinon tape 'non'.")
    return DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    date_input = update.message.text
    date_val = None if date_input.lower() == 'non' else date_input
    
    supabase.table("programmes").insert({
        "chat_id": data['chat_id'], "jour": data['jour'], "heure": data['heure'],
        "chantre": data['chantre'], "type_media": data['type'], "url_media": data['url'],
        "texte": data['texte'], "date_complete": date_val, "actif": True
    }).execute()
    await update.message.reply_text(f"✅ PROGRAMME ENREGISTRÉ !\n{data['jour']} à {data['heure']}")
    return ConversationHandler.END

async def get_id_groupe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"L'ID de ce groupe est : {update.message.chat_id}")

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("ajouter", start_ajouter)],
        states={
            ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_id_conv)],
            JOUR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_jour)],
            HEURE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_heure)],
            CHANTRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_chantre)],
            TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_type)],
            URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_url)],
            TEXTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_texte)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("get_id", get_id_groupe))
    app.job_queue.run_repeating(scan_et_envoyer, interval=60, first=10)
    app.run_polling()

if __name__ == "__main__":
    main()
