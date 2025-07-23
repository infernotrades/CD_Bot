import os
import json
import sqlite3
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Setup logger
logger = logging.getLogger(__name__)

# Admin chat ID (numeric or @handle) from environment
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "@clones_direct")

# SQLite DB path (in Fly.io volume)
DB_PATH = '/app/data/orders.db'

# Initialize DB
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  telegram_user TEXT,
                  ig_handle TEXT,
                  payment TEXT,
                  country TEXT,
                  total REAL,
                  items JSON,
                  status TEXT DEFAULT 'pending')''')
    conn.commit()
    conn.close()

init_db()

# Load & sort strains alphabetically by name
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
"""

PRICING_TEXT = """
Pricing:
• 1–2 clones: $80 each
• 3+ clones: $60 each

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

def save_order_to_db(telegram_user, ig_handle, payment, country, total, items):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO orders (timestamp, telegram_user, ig_handle, payment, country, total, items, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (datetime.now().isoformat(), telegram_user, ig_handle, payment, country, total, json.dumps(items), 'pending'))
    conn.commit()
    order_id = c.lastrowid
    conn.close()
    return order_id

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Access denied. This command is for admins only.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, timestamp, telegram_user, ig_handle, payment, country, total, items FROM orders WHERE status = 'pending'")
    orders = c.fetchall()
    conn.close()

    if not orders:
        await update.message.reply_text("No pending orders.")
        return

    for order in orders:
        order_id, timestamp, telegram_user, ig_handle, payment, country, total, items_json = order
        items = json.loads(items_json)
        lines = "\n".join(f"{it['strain']} x{it['quantity']}" for it in items)
        summary = (
            f"Order #{order_id} ({timestamp})\n"
            f"Telegram: {telegram_user}\n"
            f"Instagram: {ig_handle}\n"
            f"Payment: {payment}\n"
            f"Shipping: {country}\n"
            f"Total: ${total:.2f}\n"
            f"Items: {lines}"
        )
        keyboard = [[
            InlineKeyboardButton("Mark Completed", callback_data=f"complete_order_{order_id}"),
            InlineKeyboardButton("Delete Order", callback_data=f"delete_order_{order_id}")
        ]]
        await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    CART[uid] = {"items": [], "state": None}
    keyboard = [
        [InlineKeyboardButton("📋 View Strains", callback_data="view_strains")],
        [InlineKeyboardButton("🛒 View Cart",    callback_data="view_cart")],
        [InlineKeyboardButton("❓ FAQ",          callback_data="faq")],
    ]
    await update.message.reply_text(
        "Welcome to Clones Direct! 🌱👋 Browse elite clones and build your custom order below.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

def get_strain_buttons():
    buttons = []
    for i in range(0, len(STRAINS), 2):
        row = []
        for j in (0, 1):
            idx = i + j
            if idx < len(STRAINS):
                name = STRAINS[idx]["name"]
                row.append(InlineKeyboardButton(name, callback_data=f"strain_{idx}"))
        buttons.append(row)
    return buttons

async def send_strain_details(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str):
    strain = next((s for s in STRAINS if s["name"] == name), None)
    if not strain:
        await update.callback_query.message.reply_text("❌ Strain not found.")
        return

    uid = update.effective_user.id
    CART[uid]["last_strain"] = name

    caption = (
        f"<b>{name}</b>\n"
        f"<i>Genetics:</i> {strain['lineage']}\n"
        f"<i>Breeder:</i> {strain.get('breeder','Unknown')}\n\n"
        f"{strain.get('notes','')}"
    )
    if strain.get("breeder_url"):
        caption += f'\n\n<a href="{strain["breeder_url"]}">Breeder Info</a>'

    keyboard = [[
        InlineKeyboardButton("➕ Add to Cart", callback_data="add_quantity"),
        InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains")
    ]]
    await update.callback_query.message.reply_photo(
        photo=strain["image_url"],
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def handle_add_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    CART[uid]["state"] = "await_qty"
    keyboard = [
        [InlineKeyboardButton("1", callback_data="qty_1"), InlineKeyboardButton("2", callback_data="qty_2"), InlineKeyboardButton("3", callback_data="qty_3")],
        [InlineKeyboardButton("4", callback_data="qty_4"), InlineKeyboardButton("5", callback_data="qty_5"), InlineKeyboardButton("6", callback_data="qty_6")],
        [InlineKeyboardButton("7", callback_data="qty_7"), InlineKeyboardButton("8", callback_data="qty_8"), InlineKeyboardButton("9", callback_data="qty_9"), InlineKeyboardButton("10", callback_data="qty_10")],
    ]
    await update.callback_query.message.reply_text(
        "How many clones would you like to add? (Max 10)\n\n" + PRICING_TEXT,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # Ensure cart exists
    if uid not in CART:
        CART[uid] = {"items": [], "state": None}

    # Keyword shortcuts
    for key, action in {
        "clones":"view_strains","strains":"view_strains","menu":"view_strains",
        "how much":"faq","faq":"faq"
    }.items():
        if key in text.lower():
            await handle_callback_query_from_text(update, action)
            return

    # IG handle input
    if CART.get(uid, {}).get("state") == "await_ig":
        CART[uid]["ig_handle"] = text
        CART[uid]["state"] = None
        # Show confirmation
        items = CART[uid]["items"]
        lines = "\n".join(f"{it['strain']} x{it['quantity']}" for it in items)
        total = calculate_price(items, CART[uid]["country"], CART[uid]["payment_method"])
        summary = (
            f"🛒 Order Summary:\n{lines}\n\n"
            f"Shipping: {CART[uid]['country'].upper()}\n"
            f"Payment: {CART[uid]['payment_method']}\n"
            f"Instagram: {text}\n"
            f"Total: ${total:.2f}\n\n"
            "Looks good? Confirm to send your order."
        )
        keyboard = [[
            InlineKeyboardButton("✅ Confirm Order", callback_data="confirm_order"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_order")
        ]]
        await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Custom crypto input
    if CART.get(uid, {}).get("state") == "await_crypto_other":
        CART[uid]["payment_method"] = f"Crypto - {text.upper()}"
        CART[uid]["state"] = None
        await show_country_selection(update, context)
        return

    # Fallback for invalid inputs
    await update.message.reply_text("Please use the buttons or enter a valid command.")

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = update.callback_query.data
    uid = update.effective_user.id

    if data.startswith("complete_order_"):
        order_id = int(data.split("_")[2])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE orders SET status = 'completed' WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        await update.callback_query.message.reply_text(f"Order #{order_id} marked as completed.")
        return

    if data.startswith("delete_order_"):
        order_id = int(data.split("_")[2])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        await update.callback_query.message.reply_text(f"Order #{order_id} deleted.")
        return

    if uid not in CART:
        CART[uid] = {"items": [], "state": None}

    if data.startswith("strain_"):
        idx = int(data.split("_",1)[1])
        name = STRAINS[idx]["name"]
        await send_strain_details(update, context, name)
        return

    if data.startswith("qty_"):
        qty = int(data.split("_")[1])
        if "last_strain" not in CART[uid]:
            await update.callback_query.message.reply_text("❌ Strain not found.")
            return
        CART[uid]["items"].append({"strain": CART[uid]["last_strain"], "quantity": qty})
        del CART[uid]["last_strain"]
        CART[uid]["state"] = None
        await update.callback_query.message.reply_text(
            f"🎉 Added {CART[uid]['items'][-1]['strain']} x{qty} to your cart!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains")],
            ])
        )
        return

    if data == "view_strains":
        await update.callback_query.message.reply_text(
            "📋 Select a strain to view details:",
            reply_markup=InlineKeyboardMarkup(get_strain_buttons())
        )
    elif data == "faq":
        await update.callback_query.message.reply_text(FAQ_TEXT)
    elif data == "view_cart":
        items = CART[uid]["items"]
        if not items:
            await update.callback_query.message.reply_text("🛒 Your cart is empty.")
            return
        summary = "\n".join(f"{i+1}. {it['strain']} x{it['quantity']}" for i,it in enumerate(items))
        subtotal = calculate_subtotal(items)
        keyboard = []
        for i, it in enumerate(items):
            keyboard.append([InlineKeyboardButton(f"❌ Remove {it['strain']}", callback_data=f"remove_{i}")])
        keyboard += [
            [InlineKeyboardButton("✅ Finalize Order", callback_data="finalize_order")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains")]
        ]
        await update.callback_query.message.reply_text(
            f"🛒 <b>Your Cart</b>\n\n{summary}\n\nSubtotal: ${subtotal:.2f} (before shipping/fees)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data.startswith("remove_"):
        idx = int(data.split("_")[1])
        if idx < len(CART[uid]["items"]):
            del CART[uid]["items"][idx]
        await update.callback_query.message.reply_text("✅ Item removed. Refreshing cart...")
        dummy_query = update.callback_query
        dummy_query.data = "view_cart"
        dummy_update = Update(update.update_id, callback_query=dummy_query)
        await handle_callback_query(dummy_update, context)
    elif data == "finalize_order":
        if not CART[uid]["items"]:
            await update.callback_query.message.reply_text("🛒 Your cart is empty. Add items first!")
            return
        await update.callback_query.message.reply_text(
            "💳 Select payment method:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Crypto (No Fee)", callback_data="payment_crypto")],
                [InlineKeyboardButton("💳 PayPal (+5%)", callback_data="payment_paypal")],
                [InlineKeyboardButton("✉️ Mail In", callback_data="payment_mail_in")],
            ])
        )
    elif data.startswith("payment_"):
        method = data.split("_")[1]
        if method == "crypto":
            await update.callback_query.message.reply_text(
                "Select your crypto:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("BTC", callback_data="crypto_btc"), InlineKeyboardButton("ETH", callback_data="crypto_eth"), InlineKeyboardButton("SOL", callback_data="crypto_sol")],
                    [InlineKeyboardButton("USDC", callback_data="crypto_usdc"), InlineKeyboardButton("USDT", callback_data="crypto_usdt"), InlineKeyboardButton("Other", callback_data="crypto_other")],
                ])
            )
            return
        else:
            CART[uid]["payment_method"] = "PayPal" if method == "paypal" else "Mail In"
        await show_country_selection(update, context)
    elif data.startswith("crypto_"):
        if data == "crypto_other":
            CART[uid]["state"] = "await_crypto_other"
            await update.callback_query.message.reply_text("Enter the crypto token you wish to use (e.g., LTC)")
            return
        else:
            coin = data.split("_")[1].upper()
            CART[uid]["payment_method"] = f"Crypto - {coin}"
            await show_country_selection(update, context)
    elif data.startswith("country_"):
        country = "USA" if data == "country_usa" else "International"
        CART[uid]["country"] = country
        CART[uid]["state"] = "await_ig"
        await update.callback_query.message.reply_text("Please enter your Instagram handle (e.g., @username)")
    elif data == "confirm_order":
        items = CART[uid]["items"]
        lines = "\n".join(f"- {it['strain']} x{it['quantity']}" for it in items)
        user = update.effective_user
        uname = f"@{user.username}" if user.username else user.first_name
        total = calculate_price(items, CART[uid]["country"], CART[uid]["payment_method"])
        order_msg = (
            f"📦 <b>New Order</b>\n"
            f"• Telegram: {uname}\n"
            f"• Instagram: {CART[uid]['ig_handle']}\n"
            f"• Payment: {CART[uid]['payment_method']}\n"
            f"• Shipping: {CART[uid]['country']}\n"
            f"• Total: ${total:.2f}\n"
            f"• Items:\n{lines}"
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=order_msg,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send order to admin: {e}")

        # Save to DB regardless
        save_order_to_db(uname, CART[uid]["ig_handle"], CART[uid]["payment_method"], CART[uid]["country"], total, items)
        await update.callback_query.message.reply_text("👍 Order confirmed! We've sent it for processing. We'll reach out shortly.")
        del CART[uid]
    elif data == "cancel_order":
        await update.callback_query.message.reply_text("❌ Order canceled. Start over with /start.")
        del CART[uid]
    elif data == "add_quantity":
        await handle_add_quantity(update, context)

async def show_country_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇺🇸 USA ($40 Shipping)", callback_data="country_usa")],
        [InlineKeyboardButton("🌍 International ($100 Shipping)", callback_data="country_intl")]
    ]
    await update.effective_message.reply_text(
        "📍 Where are you shipping to? This affects your total.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_callback_query_from_text(update, action):
    class DummyCQ:
        def __init__(self, msg, a): self.message, self.data = msg, a
        async def answer(self): pass
    dummy_query = CallbackQuery(id=0, from_user=update.effective_user, chat_instance="", message=update.message, data=action)
    dummy_update = Update(update.update_id, callback_query=dummy_query)
    await handle_callback_query(dummy_update, None)