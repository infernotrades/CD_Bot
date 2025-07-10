import os
import json
import re
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, CallbackQuery
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Setup logger
logger = logging.getLogger(__name__)

# Admin chat ID from environment
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
if not ADMIN_CHAT_ID:
    logger.warning("ADMIN_CHAT_ID is not set! Orders won't be sent to admin.")

# Load & sort strains
with open("strains.json", "r") as f:
    _data = json.load(f)
STRAINS = sorted(_data, key=lambda s: s["name"].lower())

# In-memory cart storage
CART = {}

# FAQ and pricing text
FAQ_TEXT = """
Frequently Asked Questions

• Orders ship within 14 days of payment unless otherwise stated.
• Worldwide shipping.
• Strains sourced from breeders, seed hunts, or trusted nurseries.
• 7-day satisfaction guarantee.
• 1 free reship allowed (then customer covers shipping).
• All clones are grown in Oasis root cubes.
• Your Telegram and Instagram data is only used for order processing.
"""

PRICING_TEXT = """
Pricing:
• 1–2 clones: $80 each
• 3+ clones: $60 each (save $20 each!)

Shipping:
• USA: $40 (1–2 days)
• International: $100 (3–5 days)

PayPal Fee:
• +5% (applies to total including shipping)
"""

def calculate_subtotal(items):
    total_qty = sum(i["quantity"] for i in items)
    price_per = 60 if total_qty >= 3 else 80
    return total_qty * price_per

def calculate_price(items, country, payment_method):
    subtotal = calculate_subtotal(items)
    shipping = 40 if country.lower() == "usa" else 100
    fee = 0.05 * (subtotal + shipping) if "PayPal" in payment_method else 0
    return subtotal + shipping + fee

def log_order(order_msg, status="success"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("orders.log", "a") as f:
        f.write(f"[{timestamp}] {status.upper()}\n{order_msg}\n{'-'*50}\n")
    logger.info(f"Order logged with status '{status}'.")

async def handle_confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    items = CART[uid]["items"]
    lines = "\n".join(f"- {it['strain']} x{it['quantity']}" for it in items)
    user = update.effective_user
    uname = f"@{user.username}" if user.username else user.first_name
    total = calculate_price(items, CART[uid]["country"], CART[uid]["payment_method"])
    order_msg = (
        f"📦 *New Order*\n"
        f"• Telegram: {uname}\n"
        f"• Instagram: {CART[uid]['ig_handle']}\n"
        f"• Payment: {CART[uid]['payment_method']}\n"
        f"• Shipping: {CART[uid]['country']}\n"
        f"• Total: ${total:.2f}\n"
        f"• Items:\n{lines}"
    )
    log_order(order_msg, status="attempt")

    # Force log ADMIN_CHAT_ID
    logger.info(f"Sending order to ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=order_msg,
            parse_mode=ParseMode.MARKDOWN
        )
        log_order(order_msg, status="success")
        await update.callback_query.message.reply_text(
            "👍 Order confirmed! We've sent it to our team for processing. We'll reach out soon via Instagram."
        )
    except Exception as e:
        logger.error(f"Failed to DM order: {e}")
        await update.callback_query.message.reply_text(
            f"⚠️ Failed to notify admin. Order saved internally.\nError: {e}"
        )
    del CART[uid]

# PATCH: Use this instead of old confirm logic
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = update.callback_query.data
    uid = update.effective_user.id

    if data == "confirm_order":
        await handle_confirm_order(update, context, uid)
        return

    # Your other callback code goes here (keep the rest of your bot logic untouched)
    # ...