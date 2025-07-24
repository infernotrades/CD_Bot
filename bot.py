# bot.py
import os
import logging
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from handlers import start_command, handle_text, handle_callback_query, faq, list_orders, remind_pending, backup_db

# Fly.io health-check listener
def _serve_healthcheck():
    port = int(os.getenv("PORT", 8080))
    HTTPServer(("", port), SimpleHTTPRequestHandler).serve_forever()
threading.Thread(target=_serve_healthcheck, daemon=True).start()

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Global error handler
async def error_handler(update: object, context):
    logger.error("Exception while handling update:", exc_info=context.error)

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN missing")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("help", faq))
    app.add_handler(CommandHandler("faq", faq))
    app.add_handler(CommandHandler("orders", list_orders))
    app.add_handler(CommandHandler("remind", remind_pending))
    app.add_handler(CommandHandler("backup", backup_db))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    # Job queue for reminders and cleanups
    job_queue = app.job_queue
    job_queue.run_repeating(clean_abandoned_carts, interval=3600, first=3600)  # Hourly cart cleanup
    job_queue.run_repeating(auto_remind_pending, interval=172800, first=172800)  # Every 48 hours

    print("✅ Bot is running in POLLING mode...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

async def whoami(update: Update, context):
    await update.message.reply_text(f"Your chat_id is: {update.effective_chat.id}")
