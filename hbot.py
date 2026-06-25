import os
import threading
import logging
from datetime import datetime
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

# Logging
logging.basicConfig(level=logging.INFO)

# Flask pour satisfaire Render
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "H-BOT est en ligne chef 💚"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app_flask.run(host='0.0.0.0', port=port)

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salut chef 💪 H-BOT est prêt.\n/rappel 20:00 Ton texte")

async def rappel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        heure_str = context.args[0]
        texte = " ".join(context.args[1:])
        user_id = update.effective_user.id
        heure = datetime.strptime(heure_str, "%H:%M").time()
        now = datetime.now(TZ)
        prochain = datetime.combine(now.date(), heure, tzinfo=TZ)
        if prochain < now: prochain = prochain.replace(day=now.day + 1)
        data = supabase.table("rappels").insert({"user_id": user_id, "heure": heure_str, "texte": texte, "actif": True}).execute()
        rappel_id = data.data[0]["id"]
        delay = (prochain - now).total_seconds()
        context.job_queue.run_once(send_rappel, delay, chat_id=update.effective_chat.id, data={"texte": texte, "rappel_id": rappel_id})
        await update.message.reply_text(f"✅ Rappel calé pour {heure_str} chef\nID: {rappel_id}")
    except:
        await update.message.reply_text("Format: /rappel 20:00 Ton texte chef")

async def send_rappel(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(job.chat_id, text=f"🔔 RAPPEL CHEF:\n{job.data['texte']}")

async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = supabase.table("rappels").select("*").eq("user_id", user_id).eq("actif", True).execute()
    if not data.data:
        await update.message.reply_text("Aucun rappel actif chef")
        return
    msg = "📋 Tes rappels:\n\n"
    for r in data.data:
        msg += f"ID {r['id']} | {r['heure']} → {r['texte']}\n"
    await update.message.reply_text(msg)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rappel_id = int(context.args[0])
        user_id = update.effective_user.id
        supabase.table("rappels").update({"actif": False}).eq("id", rappel_id).eq("user_id", user_id).execute()
        await update.message.reply_text(f"🗑️ Rappel {rappel_id} supprimé chef")
    except:
        await update.message.reply_text("Format: /stop ID")

async def parler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(f"Salut {user_name} chef 💪 Dis /aide pour voir ce que je peux faire.")

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rappel", rappel))
    app.add_handler(CommandHandler("liste", liste))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, parler))
    print("H-BOT LANCÉ CHEF 🔥")
    app.run_polling()

if __name__ == "__main__":
    main()
