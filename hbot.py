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

# Étapes de la conversation. AJOUT: AJOUT_CHANTRE_NOM, AJOUT_CHANTRE_PHOTO
ID, HEURE, DATE, CHANTRE, TYPE, URL, TEXTE, CONTINUER, AJOUT_CHANTRE_NOM, AJOUT_CHANTRE_PHOTO = range(10)

# --- FLASK ---
app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "H-BOT V8 PHOTO CHANTRES opérationnel chef 💚"

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
        
        if db_heure == heure_actuelle and p['date_complete'] == today_date:
            chat_id = int(p['chat_id']) # <-- FIX BUG INT
            msg = f"🔔 PROGRAMME: {p['chantre']}\n\n{p['texte']}"
            try:
                # 1. ENVOIE LE MESSAGE PRINCIPAL
                if p['type_media'] == "image": 
                    await context.bot.send_photo(chat_id=chat_id, photo=p['url_media'], caption=msg)
                elif p['type_media'] == "video": 
                    await context.bot.send_video(chat_id=chat_id, video=p['url_media'], caption=msg)
                elif p['type_media'] == "vocal": 
                    await context.bot.send_voice(chat_id=chat_id, voice=p['url_media'], caption=msg)
                else: 
                    await context.bot.send_message(chat_id=chat_id, text=msg)
                
                # 2. NOUVEAUTÉ: SCANNE LE TEXTE ET ENVOIE LES PHOTOS DES CHANTRES
                texte_upper = p['texte'].upper()
                chantres_db = supabase.table("chantres").select("*").execute()
                for c in chantres_db.data:
                    if c['nom'].upper() in texte_upper: # Si "MARINA" est dans le texte
                        await context.bot.send_photo(chat_id=chat_id, photo=c['photo_url'], caption=f"🎤 {c['nom']}")
                        print(f"   -> Photo de {c['nom']} envoyée")

                print(f"✅ PROGRAMME ENVOYÉ A {chat_id}")
                supabase.table("programmes").update({"actif": False}).eq("id", p['id']).execute()
                
            except Exception as e: print(f"❌ Erreur envoi: {e}")

# --- HANDLERS CONVERSATION AJOUTER ---
async def start_ajouter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Quel est l'ID du groupe ? (/get_id dans le groupe pour le savoir)")
    return ID

async def get_id_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['chat_id'] = int(update.message.text) # <-- FIX BUG INT
    except:
        await update.message.reply_text("❌ L'ID doit être que des chiffres. Refais /ajouter")
        return ConversationHandler.END
    await update.message.reply_text("Heure ? (format HH:MM)")
    return HEURE

async def get_heure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: datetime.strptime(update.message.text, "%H:%M")
    except: 
        await update.message.reply_text("❌ Mauvais format. Ex: 10:30")
        return HEURE
    context.user_data['heure'] = update.message.text
    await update.message.reply_text("Date précise (JJ/MM/AAAA) ?")
    return DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: datetime.strptime(update.message.text, "%d/%m/%Y")
    except: 
        await update.message.reply_text("❌ Mauvais format. Ex: 04/07/2026")
        return DATE
    context.user_data['date'] = update.message.text
    await update.message.reply_text("Chantre / Titre du programme ?")
    return CHANTRE

async def get_chantre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chantre'] = update.message.text
    await update.message.reply_text("Type de média ? (image, video, vocal, ou tape skip)")
    return TYPE

async def get_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == 'skip':
        context.user_data['type'] = 'texte'
        context.user_data['url'] = 'none'
        await update.message.reply_text("Texte du message :\nEx: Adoration: MARINA\nCélébration: JOANA")
        return TEXTE
    context.user_data['type'] = update.message.text.lower()
    await update.message.reply_text("Lien URL du média (ou tape skip) :")
    return URL

async def get_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['url'] = 'none' if update.message.text.lower() == 'skip' else update.message.text
    await update.message.reply_text("Texte du message :\nEx: Adoration: MARINA\nCélébration: JOANA")
    return TEXTE

async def get_texte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    data['texte'] = update.message.text
    
    supabase.table("programmes").insert({
        "chat_id": data['chat_id'], "jour": "PONCTUEL", "heure": data['heure'],
        "chantre": data['chantre'], "type_media": data['type'], "url_media": data['url'],
        "texte": data['texte'], "date_complete": data['date'], "actif": True
    }).execute()
    
    keyboard = [[InlineKeyboardButton("✅ Oui, ajouter un autre", callback_data="oui"), InlineKeyboardButton("❌ Non, stop", callback_data="non")]]
    await update.message.reply_text(f"✅ PROGRAMME VALIDÉ CHEF !\n\n📅 {data['date']} à {data['heure']}\n\nTu veux ajouter un autre ?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CONTINUER

async def continuer_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "oui":
        await query.edit_message_text("Ok on enchaîne 👊\n\nQuel est l'ID du groupe ?")
        return ID
    else:
        await query.edit_message_text("Programme terminé Chef. /ajouter pour recommencer.")
        return ConversationHandler.END

# --- NOUVEAUX HANDLERS CHANTRE ---
async def start_ajout_chantre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Nom du chantre à enregistrer ? Ex: MARINA")
    return AJOUT_CHANTRE_NOM

async def get_nom_chantre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nom_chantre'] = update.message.text.upper()
    await update.message.reply_text(f"Ok. Envoie maintenant la photo de {update.message.text}")
    return AJOUT_CHANTRE_PHOTO

async def get_photo_chantre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nom = context.user_data['nom_chantre']
    photo_file = await update.message.photo[-1].get_file()
    photo_url = photo_file.file_path # Railway garde le lien temp. Mieux: upload sur imgbb
    
    supabase.table("chantres").upsert({"nom": nom, "photo_url": photo_url}).execute() # upsert = ajoute ou modifie
    await update.message.reply_text(f"✅ {nom} enregistré ! Sa photo sera envoyée auto si son nom est dans le programme.")
    return ConversationHandler.END

# --- AUTRES COMMANDES ---
async def get_id_groupe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"L'ID de ce groupe est : `{update.message.chat_id}`", parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("H-BOT V8 PHOTO CHANTRES prêt chef !\n\nCommandes :\n/ajouter - Programmer\n/ajouter_chantre - Enregistrer photo d'un chantre\n/get_id - ID du groupe\n/cancel - Annuler")

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Annulé chef.")
    return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    
    conv_ajouter = ConversationHandler(
        entry_points=[CommandHandler("ajouter", start_ajouter)],
        states={
            ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_id_conv)],
            HEURE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_heure)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            CHANTRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_chantre)],
            TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_type)],
            URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_url)],
            TEXTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_texte)],
            CONTINUER: [CallbackQueryHandler(continuer_conv)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )
    
    conv_chantre = ConversationHandler(
        entry_points=[CommandHandler("ajouter_chantre", start_ajout_chantre)],
        states={
            AJOUT_CHANTRE_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nom_chantre)],
            AJOUT_CHANTRE_PHOTO: [MessageHandler(filters.PHOTO, get_photo_chantre)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_ajouter)
    app.add_handler(conv_chantre)
    app.add_handler(CommandHandler("get_id", get_id_groupe))
    app.job_queue.run_repeating(scan_et_envoyer, interval=60, first=10)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
