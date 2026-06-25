import os
import threading
import logging
from datetime import datetime, time
import pytz
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client, Client

# Configuration
TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TZ = pytz.timezone("Africa/Abidjan")

logging.basicConfig(level=logging.INFO)
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "H-BOT est en ligne chef 💚"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app_flask.run(host='0.0.0.0', port=port)

# --- LOGIQUE DE RECHARGEMENT ---
async def recharger_rappels(context: ContextTypes.DEFAULT_TYPE):
    """Relance les rappels actifs depuis Supabase."""
    try:
        data = supabase.table("rappels").select("*").eq("actif", True).execute()
        now = datetime.now(TZ)
        
        for r in data.data:
            heure_obj = datetime.strptime(r["heure"], "%H:%M").time()
            prochain = datetime.combine(now.date(), heure_obj, tzinfo=TZ)
            
            # Si l'heure est passée, on programme pour demain
            if prochain < now:
                prochain = prochain.replace(day=now.day + 1)
            
            delay = (prochain - now).total_seconds()
            context.job_queue.run_once(
                send_rappel, delay, 
                chat_id=r["user_id"], 
                data={"texte": r["texte"], "rappel_id": r["id"]}
            )
        logging.info(f"✅ {len(data.data)} rappels rechargés.")
    except Exception as e:
        logging.error(f"Erreur rechargement : {e}")

# --- HANDLERS (RAPPEL) ---
async def send_rappel(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(job.chat_id, text=f"🔔 RAPPEL CHEF:\n{job.data['texte']}")

# ... (tes autres handlers start, liste, stop, etc. restent identiques)

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    
    # Lancer le rechargement dès le démarrage
    app.job_queue.run_once(recharger_rappels, 1)
    
    # Tes handlers habituels
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rappel", rappel))
    # ... le reste ...
    
    print("H-BOT LANCÉ ET SYNCHRONISÉ CHEF 🔥")
    app.run_polling()

if __name__ == "__main__":
    main()
