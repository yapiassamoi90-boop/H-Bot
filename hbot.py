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

# Flask
app_flask = Flask(__name__)
@app_flask.route('/')
def home():
    return "H-BOT est en ligne chef 💚"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app_flask.run(host='0.0.0.0', port=port)

# --- AUTOMATISATION ---
async def scan_et_envoyer(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(TZ)
    heure_actuelle = now.strftime("%H:%M")
    jour_actuel = now.strftime("%A") 
    response = supabase.table("programmes").select("*").eq("jour", jour_actuel).eq("heure", heure_actuelle).eq("actif", True).execute()
    for p in response.data:
        msg = f"🔔 PROGRAMME: {p['chantre']}\n\n{p['texte']}"
        try:
            if p['type_media'] == "image": await context.bot.send_photo(p['chat_id'], photo=p['url_media'], caption=msg)
            elif p['type_media'] == "video": await context.bot.send_video(p['chat_id'], video=p['url_media'], caption=msg)
            elif p['type_media'] == "vocal": await context.bot.send_voice(p['chat_id'], voice=p['url_media'], caption=msg)
        except Exception as e: print(f"Erreur envoi auto: {e}")

async def ajouter_programme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args # Format: /ajouter_programme ID Jour Heure Chantre Type URL Texte
        supabase.table("programmes").insert({
            "chat_id": args[0], "jour": args[1], "heure": args[2], "chantre": args[3],
            "type_media": args[4], "url_media": args[5], "texte": " ".join(args[6:]), "actif": True
        }).execute()
        await update.message.reply_text("✅ Programme enregistré, chef !")
    except: await update.message.reply_text("Format: /ajouter_programme ID Jour Heure Chantre type(image/video/vocal) URL Texte")

# --- NOUVELLE FONCTION GET_ID ---
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"L'ID de ce groupe est : {chat_id}")

# --- HANDLERS MÉDIAS ---
async def envoyer_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo="https://picsum.photos/400/300", caption="Tiens chef, une image ! 📸")

async def envoyer_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_video(chat_id=update.effective_chat.id, video="https://www.w3schools.com/html/mov_bbb.mp4", caption="Voici ta vidéo chef ! 🎥")

async def envoyer_vocal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_voice(chat_id=update.effective_chat.id, voice="https://actions.google.com/sounds/v1/alarms/beep_short.ogg", caption="Voici le vocal chef ! 🔊")

# --- HANDLERS RAPPELS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salut chef 💪 H-BOT est opérationnel.\n\nCommandes:\n/get_id (pour l'ID groupe)\n/rappel 20:00 Texte\n/liste\n/stop ID\n/image\n/video\n/vocal\n/ajouter_programme ID Jour Heure Chantre type URL Texte")

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
    await context.bot.send_message(context.job.chat_id, text=f"🔔 RAPPEL CHEF:\n{context.job.data['texte']}")

async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = supabase.table("rappels").select("*").eq("user_id", update.effective_user.id).eq("actif", True).execute()
    if not data.data: await update.message.reply_text("Aucun rappel actif chef")
    else: await update.message.reply_text("📋 Tes rappels:\n" + "\n".join([f"ID {r['id']} | {r['heure']} → {r['texte']}" for r in data.data]))

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        supabase.table("rappels").update({"actif": False}).eq("id", int(context.args[0])).execute()
        await update.message.reply_text("🗑️ Rappel supprimé chef")
    except: await update.message.reply_text("Format: /stop ID")

async def parler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Dis /start pour voir ce que je peux faire chef 💪")

# --- MAIN ---
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    
    # Automatisation
    app.job_queue.run_repeating(scan_et_envoyer, interval=60, first=10)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get_id", get_id)) # Ajout de la commande ID
    app.add_handler(CommandHandler("rappel", rappel))
    app.add_handler(CommandHandler("liste", liste))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("image", envoyer_image))
    app.add_handler(CommandHandler("video", envoyer_video))
    app.add_handler(CommandHandler("vocal", envoyer_vocal))
    app.add_handler(CommandHandler("ajouter_programme", ajouter_programme))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, parler))
    
    print("H-BOT LANCÉ CHEF 🔥")
    app.run_polling()

if __name__ == "__main__":
    main()
