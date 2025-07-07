# bot.py

import os
import logging
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from handlers import start_command, handle_text, handle_callback_query

#––– START fly.io healthcheck shim ––––––––––––––––––––––––––––––––
def _serve_healthcheck():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("", port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=_serve_healthcheck, daemon=True).start()
#––– END fly.io healthcheck shim ––––––––––––––––––––––––––––––––

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Debug handler to reveal numeric chat_id
async def whoami(update: Update, context):
    await update.message.reply_text(f"Your chat_id is: {update.effective_chat.id}")

# Global error handler
async def error_handler(update: object, context):
    logger.error("Exception while handling update:", exc_info=context.error)

def main():
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("✅ Bot is running in POLLING mode...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
