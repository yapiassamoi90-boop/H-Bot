import os
import threading
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from supabase import create_client, Client
from flask import Flask

# Config
TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TZ = pytz.timezone("Africa/Abidjan")

# Web Server
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "H-BOT is alive and running chef 💚"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app_flask.run(host='0.0.0.0', port=port)

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salut chef 💪 H-BOT est prêt.\n/rappel 20:00 Ton texte")

async def rappel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (ta logique existante ici) ...
    pass

async def send_rappel(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(job.chat_id, text=f"🔔 RAPPEL CHEF:\n{job.data['texte']}")

async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (ta logique existante ici) ...
    pass

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (ta logique existante ici) ...
    pass

async def parler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (ta logique existante ici) ...
    pass

# --- MAIN ---
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    
    app = Application.builder().token(TOKEN).build()
    
    # Les fonctions sont maintenant définies AVANT d'être ajoutées ici
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rappel", rappel))
    app.add_handler(CommandHandler("liste", liste))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, parler))
    
    print("H-BOT LANCÉ CHEF 🔥")
    app.run_polling()

if __name__ == "__main__":
    main()
