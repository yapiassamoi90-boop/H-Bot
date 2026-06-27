import os
import threading
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, ContextTypes, MessageHandler, 
                          filters, ConversationHandler, CallbackQueryHandler)
from supabase import create_client, Client
from flask import Flask

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TZ = pytz.timezone("Africa/Abidjan")

# Étapes de la conversation. On vire JOUR
ID, HEURE, CHANTRE, TYPE, URL, TEXTE, DATE, CONTINUER = range(8)

# --- FLASK (POUR RAILWAY) ---
app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "H-BOT V7 PONCTUEL opérationnel chef 💚"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app_flask.run(host='0.0.0.0', port=port)

# --- LOGIQUE DE SCAN ---
async def scan_et_envoyer(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(TZ)
    today_date = now.strftime("%d/%m/%Y")
    heure_actuelle = now.strftime("%H:%M")
    
    print(f"[{heure_actuelle}] Scan en cours...")
    
    response = supabase.table("programmes").select("*").eq("actif", True).execute()
    for p in response.data:
        db_heure = str(p['heure'])
        if ":" in db_heure: db_heure = ":".join(db_heure.split(":")[:2])
        
        if db_heure == heure_actuelle and p['date_complete'] == today_date: # <-- UNIQUEMENT DATE EXACTE
            msg = f"🔔 PROGRAMME: {p['chantre']}\n\n{p['texte']}"
            try:
                if p['type_media'] == "image": await context.bot.send_photo(p['chat_id'], photo=p['url_media'], caption=msg)
                elif p['type_media'] == "video": await context.bot.send_video(p['chat_id'], video=p['url_media'], caption=msg)
                elif p['type_media'] == "vocal": await context.bot.send_voice(p['chat_id'], voice=p['url_media'], caption=msg)
                else: await context.bot.send_message(p['chat_id'], text=msg)
                
                print(f"✅ ENVOYE A {p['chat_id']} POUR {p['chantre']}")
                supabase.table("programmes").update({"actif": False}).eq("id", p['id']).execute() # <-- Il meurt après 1 envoi
                
            except Exception as e: print(f"❌ Erreur envoi: {e}")

# --- HANDLERS CONVERSATION ---
async def start_ajouter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Quel est l'ID du groupe ? (/get_id dans le groupe pour le savoir)")
    return ID

async def get_id_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.message.text
    await update.message.reply_text("Heure ? (format HH:MM)")
    return HEURE

async def get_heure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['heure'] = update.message.text
    await update.message.reply_text("Date précise (JJ/MM/AAAA) ?")
    return DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE): # <-- DATE AVANT CHANTRE
    context.user_data['date'] = update.message.text
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
    data = context.user_data
    data['texte'] = update.message.text
    
    supabase.table("programmes").insert({
        "chat_id": data['chat_id'], "jour": "PONCTUEL", "heure": data['heure'],
        "chantre": data['chantre'], "type_media": data['type'], "url_media": data['url'],
        "texte": data['texte'], "date_complete": data['date'], "actif": True
    }).execute()
    
    # <-- CONFIRMATION + BOUTON CONTINUER
    keyboard = [[InlineKeyboardButton("✅ Oui, ajouter un autre", callback_data="oui"), InlineKeyboardButton("❌ Non, stop", callback_data="non")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = f"✅ PROGRAMME VALIDÉ CHEF !\n\n📅 Date: {data['date']}\n⏰ Heure: {data['heure']}\n\nTu veux ajouter un autre programme ?"
    await update.message.reply_text(msg, reply_markup=reply_markup)
    return CONTINUER

async def continuer_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "oui":
        await query.edit_message_text("Ok on enchaîne 👊\n\nQuel est l'ID du groupe ?")
        return ID
    else:
        await query.edit_message_text("Programme terminé Chef. /ajouter pour recommencer plus tard.")
        return ConversationHandler.END

async def get_id_groupe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"L'ID de ce groupe est : {update.message.chat_id}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("H-BOT V7 PONCTUEL prêt chef ! Commandes : /ajouter, /get_id, /cancel")

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Annulé chef.")
    return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("ajouter", start_ajouter)],
        states={
            ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_id_conv)],
            HEURE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_heure)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            CHANTRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_chantre)],
            TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_type)],
            URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_url)],
            TEXTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_texte)],
            CONTINUER: [CallbackQueryHandler(continuer_conv)], # <-- Le bouton
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("get_id", get_id_groupe))
    app.job_queue.run_repeating(scan_et_envoyer, interval=60, first=10)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
