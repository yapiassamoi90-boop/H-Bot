import os
import threading
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes, MessageHandler, 
                          filters, ConversationHandler)
from supabase import create_client, Client
from flask import Flask

# Config
TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TZ = pytz.timezone("Africa/Abidjan")

# Étapes de la conversation
ID, JOUR, HEURE, CHANTRE, TYPE, URL, TEXTE = range(7)

# Flask
app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "H-BOT est en ligne chef 💚"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app_flask.run(host='0.0.0.0', port=port)

# --- CONVERSATION GUIDÉE V2 ---
async def start_ajouter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("C'est parti chef ! Quel est l'ID du groupe ?")
    return ID

async def get_id_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.message.text
    await update.message.reply_text("Noté. Quel jour ? (ex: Monday, Tuesday...)")
    return JOUR

async def get_jour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['jour'] = update.message.text
    await update.message.reply_text("OK. Quelle heure ? (format HH:MM)")
    return HEURE

async def get_heure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['heure'] = update.message.text
    await update.message.reply_text("C'est qui le chantre ?")
    return CHANTRE

async def get_chantre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chantre'] = update.message.text
    await update.message.reply_text("Type de média ? (image, video, vocal, ou tape skip)")
    return TYPE

async def get_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == 'skip':
        context.user_data['type'] = 'texte'
        context.user_data['url'] = 'none'
        await update.message.reply_text("OK pas de média. Envoie-moi le texte du message :")
        return TEXTE
    
    context.user_data['type'] = update.message.text
    await update.message.reply_text("Envoie-moi le lien (URL) du média, ou tape skip :")
    return URL

async def get_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == 'skip':
        context.user_data['url'] = 'none'
    else:
        context.user_data['url'] = update.message.text
    await update.message.reply_text("Enfin, quel est le texte du message ?")
    return TEXTE

async def get_texte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    try:
        supabase.table("programmes").insert({
            "chat_id": data['chat_id'], "jour": data['jour'], "heure": data['heure'],
            "chantre": data['chantre'], "type_media": data['type'], "url_media": data['url'],
            "texte": update.message.text, "actif": True
        }).execute()
        await update.message.reply_text("✅ PROGRAMME VALIDÉ ET ENREGISTRÉ CHEF ! Tout est en place.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur Supabase: {e}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Programmation annulée, chef.")
    return ConversationHandler.END

# --- RESTE DU CODE ---
async def scan_et_envoyer(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(TZ)
    heure_actuelle = now.strftime("%H:%M")
    jour_actuel = now.strftime("%A") 
    response = supabase.table("programmes").select("*").eq("jour", jour_actuel).eq("heure", heure_actuelle).eq("actif", True).execute()
    for p in response.data:
        msg = f"🔔 PROGRAMME: {p['chantre']}\n\n{p['texte']}"
        try:
            if p['type_media'] == "image" and p['url_media'] != 'none': 
                await context.bot.send_photo(p['chat_id'], photo=p['url_media'], caption=msg)
            elif p['type_media'] == "video" and p['url_media'] != 'none': 
                await context.bot.send_video(p['chat_id'], video=p['url_media'], caption=msg)
            elif p['type_media'] == "vocal" and p['url_media'] != 'none': 
                await context.bot.send_voice(p['chat_id'], voice=p['url_media'], caption=msg)
            else:
                await context.bot.send_message(p['chat_id'], text=msg)
        except Exception as e: print(f"Erreur envoi auto: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salut chef 💪 H-BOT V2 est opérationnel.\n\nCommandes:\n/ajouter (pour créer un programme)\n/get_id /liste /stop ID")

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
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.job_queue.run_repeating(scan_et_envoyer, interval=60, first=10)
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    
    print("H-BOT VERSION PRO LANCÉ CHEF 🔥")
    app.run_polling()

if __name__ == "__main__":
    main()
