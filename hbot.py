import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8831623929:AAEP4orw6pjCRmQVOAFatHn1wkJlpm7lmBE"
rappels = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Chef, je suis prêt 💪\n\nTape /rappel 20:00 Bois de l'eau")

async def rappel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Format : /rappel 20:30 Ton message")
        return
    heure = context.args[0]
    message = " ".join(context.args[1:])
    chat_id = update.effective_chat.id
    rappels.append({"id": len(rappels)+1, "chat_id": chat_id, "heure": heure, "message": message, "actif": True})
    await update.message.reply_text(f"✅ Rappel calé pour {heure} chef :\n{message}")

async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    actifs = [r for r in rappels if r["actif"]]
    if not actifs:
        await update.message.reply_text("Aucun rappel actif chef")
        return
    txt = "📋 Tes rappels :\n\n"
    for r in actifs:
        txt += f"ID {r['id']} - {r['heure']} : {r['message']}\n"
    await update.message.reply_text(txt)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Format : /stop 3")
        return
    rappel_id = int(context.args[0])
    for r in rappels:
        if r["id"] == rappel_id:
            r["actif"] = False
            await update.message.reply_text(f"❌ Rappel {rappel_id} supprimé")
            return

async def check_rappels(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now().strftime("%H:%M")
    for r in rappels:
        if r["heure"] == now and r["actif"]:
            await context.bot.send_message(chat_id=r["chat_id"], text=f"⏰ RAPPEL CHEF :\n{r['message']}")
            r["actif"] = False

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rappel", rappel))
    app.add_handler(CommandHandler("liste", liste))
    app.add_handler(CommandHandler("stop", stop))

    async def parler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = update.message.text.lower()
    user_name = update.effective_user.first_name
    
    if any(mot in texte for mot in ["salut", "slt", "hello", "yo", "coucou"]):
        await update.message.reply_text(f"Salut {user_name} chef 💪 Tu veux quoi ?")
    elif any(mot in texte for mot in ["ça va", "cv", "tu vas bien"]):
        await update.message.reply_text("Toujours opérationnel pour toi chef 🤖 Tu veux un rappel ?")
    elif any(mot in texte for mot in ["merci", "thanks", "thx"]):
        await update.message.reply_text("Avec plaisir chef 🙏 Je suis là pour ça")
    elif any(mot in texte for mot in ["aide", "help"]):
        await update.message.reply_text("Je gère tes rappels chef 📋\n\n/rappel 20:00 Texte\n/liste pour voir\n/stop ID pour supprimer")
    else:
        await update.message.reply_text("J'ai pas tout capté chef 😅\nDis /aide ou cale un /rappel 20:00")

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, parler))
    job_queue = app.job_queue
    job_queue.run_repeating(check_rappels, interval=60, first=10)
    print("H-BOT LANCÉ CHEF 🤖 SANS SUPABASE")
    app.run_polling()

if __name__ == "__main__":
    main()
