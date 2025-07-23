import os
import logging
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from handlers import start_command, handle_text, handle_callback_query

# ─── Fly.io health-check listener ──────────────────────────────────────
def _serve_healthcheck():
    port = int(os.getenv("PORT", 8080))
    HTTPServer(("", port), SimpleHTTPRequestHandler).serve_forever()
threading.Thread(target=_serve_healthcheck, daemon=True).start()

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Debug command to reveal numeric chat_id
async def whoami(update: Update, context):
    await update.message.reply_text(f"Your chat_id is: {update.effective_chat.id}")

# Test DM command to verify admin notification
async def test_dm(update: Update, context):
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not admin_chat_id:
        await update.message.reply_text("ADMIN_CHAT_ID not set!")
        return
    try:
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text="This is a test DM from the /test_dm command to verify notifications work."
        )
        await update.message.reply_text("Test DM sent successfully to admin!")
    except Exception as e:
        logger.error(f"Test DM failed: {e}")
        await update.message.reply_text(f"Test DM failed: {e}")

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
    app.add_handler(CommandHandler("test_dm", test_dm))  # Added for debugging
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("✅ Bot is running in POLLING mode...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
