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
DB_PATH = '/data/orders.db'

initialized = False

# Initialize DB
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
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

def ensure_db():
    global initialized
    if not initialized:
        try:
            init_db()
            initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")

# Load strains with error handling
try:
    with open("strains.json", "r") as f:
        _data = json.load(f)
    STRAINS = sorted(_data, key=lambda s: s["name"].lower())
except FileNotFoundError:
    logger.error("strains.json not found")
    STRAINS = []
except json.JSONDecodeError:
    logger.error("Invalid strains.json format")
    STRAINS = []

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

For additional help, DM <a href="https://t.me/Clones_Direct">@Clones_Direct</a>
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
    fee = 0.05 * (subtotal + shipping) if "paypal" in payment_method.lower() else 0
    return subtotal + shipping + fee

def save_order_to_db(telegram_user, ig_handle, payment, country, total, items):
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO orders (timestamp, telegram_user, ig_handle, payment, country, total, items, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (datetime.now().isoformat(), telegram_user, ig_handle, payment, country, total, json.dumps(items), 'pending'))
    conn.commit()
    order_id = c.lastrowid
    conn.close()
    return order_id

def update_order_status(order_id, status):
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()

def delete_order(order_id):
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

def log_order(msg, status="success"):
    log_path = os.path.join(os.path.dirname(DB_PATH), "order_log.txt")
    with open(log_path, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] [{status.upper()}] {msg}\n")

async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(FAQ_TEXT, parse_mode=ParseMode.HTML)

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.effective_chat.id)
    admin_id_str = str(ADMIN_CHAT_ID).lstrip('@')  # Handle @prefix
    if chat_id_str != admin_id_str and update.effective_user.username != "Clones_Direct":
        await update.message.reply_text("❌ Unauthorized.")
        return
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE status = 'pending'")
    orders = c.fetchall()
    conn.close()
    if not orders:
        await update.message.reply_text("No pending orders.")
        return
    for order in orders:
        order_id, timestamp, tg_user, ig, payment, country, total, items_json, status = order
        items = json.loads(items_json)
        lines = "\n".join(f"- {it['strain']} x{it['quantity']}" for it in items)
        msg = f"Order #{order_id} ({timestamp})\nTG: {tg_user}\nIG: {ig}\nPayment: {payment}\nCountry: {country}\nTotal: ${total:.2f}\nItems:\n{lines}"
        keyboard = [
            [InlineKeyboardButton("✅ Complete", callback_data=f"complete_{order_id}")],
            [InlineKeyboardButton("❌ Delete", callback_data=f"delete_{order_id}")]
        ]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    CART[uid] = {"items": [], "state": None}
    keyboard = [
        [InlineKeyboardButton("📋 View Strains", callback_data="view_strains")],
        [InlineKeyboardButton("🛒 View Cart",    callback_data="view_cart")],
        [InlineKeyboardButton("❓ FAQ",          callback_data="faq")],
    ]
    await update.message.reply_text(
        "Welcome to Clones Direct! 🌱👋 Browse elite clones and build your custom order below.\n\nBy using this bot, you confirm you're 21+ and in a legal area.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

def get_strain_buttons():
    buttons = []
    if not STRAINS:
        return [[InlineKeyboardButton("No strains available", callback_data="noop")]]
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
    try:
        await update.callback_query.message.reply_photo(
            photo=strain["image_url"],
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        logger.error(f"Failed to send strain photo: {e}")
        await update.callback_query.message.reply_text(
            caption + "\n\n⚠️ Image unavailable.",
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

async def show_confirmation_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, ig_handle: str):
    uid = update.effective_user.id
    CART[uid]["ig_handle"] = ig_handle
    CART[uid]["state"] = None
    items = CART[uid]["items"]
    lines = "\n".join(f"{it['strain']} x{it['quantity']}" for it in items)
    total = calculate_price(items, CART[uid]["country"], CART[uid]["payment_method"])
    summary = (
        f"🛒 Order Summary:\n{lines}\n\n"
        f"Shipping: {CART[uid]['country'].upper()}\n"
        f"Payment: {CART[uid]['payment_method']}\n"
        f"Instagram: {ig_handle}\n"
        f"Total: ${total:.2f}\n\n"
        "By confirming, you verify you're 21+ and in a legal area. Proceed?"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Confirm & Submit", callback_data="confirm_order"),
        InlineKeyboardButton(" Great, from the Medium article , they use DB_PATH = "/data/app.db"

mount destination = "/data"

In code, connect and create table.

No mention of permissions issues.

They use Dockerfile? The article mentions analogous to Docker mount, but for build, perhaps buildpack.

In code, they use aiosqlite, async.

But no try except, just connect.

Perhaps no permission issue in their case.

For our code, perhaps change DB_PATH to "/data/orders.db"

And mount destination = "/data"

Also, os.makedirs not needed, since connect creates the file if not exist.

sqlite3.connect creates the DB file if not.

If dir not writable, fails.

In Fly, the mount /data is writable by app user.

Perhaps in my code, /app/data is inside /app, which is code dir, perhaps read-only? No, /app is writable.

But to match, change to /data

Also, in article, they create volume sqlite_data -s 1 -r ams

scale count 1

Yes.

In our, single machine.

For permissions, if issue, in ssh console, check ls -la /data

If owned by root, then problem.

From , yes, owned by root, app can't write.

Solution in thread: "The volume is mounted as root, but the app runs as non-root. To fix, I used a custom Dockerfile and ran as root."

Or, "Add USER root in Dockerfile."

Since no Dockerfile, perhaps create one.

For Python, to use buildpack with root, hard.

Use heroku buildpack or something.

To fix, suggest creating Dockerfile.

Simple Dockerfile for Python app.

From python:3.12-slim

COPY . /app

WORKDIR /app

RUN pip install -r requirements.txt

CMD ["python", "bot.py"]

And add USER root ? No, by default root.

But Fly buildpacks run as non-root for security.

If use Dockerfile, can run as root.

Yes.

From community, for SQLite, some use LiteFS, but for simple, run as root with Dockerfile.

Let's do that.

Provide Dockerfile.

In fly.toml, [build] dockerfile = "Dockerfile"

Then, deploy will build from Dockerfile.

Since user used --image, but now with Dockerfile, it will build new.

Also, in Dockerfile, can chown /data, but since volume mounted at runtime, can't.

Volume is mounted at runtime, empty first time, owned by root? 

From post, the mount is owned by root.

To fix, perhaps init script that chowns.

But since no sudo, hard.

Run app as root.

Yes, in Dockerfile, don't set USER, default root.

Fly allows it, but security risk.

But for bot, ok.

Yes.

Let's see thread 

Link: https://community.fly.io/t/cant-create-sqlite-database-in-mounted-volume/2925

Browse it.

Instructions: "Extract the solution for permissions issue with SQLite on volume."

Call tool.#### `bot.py`
```python
import os
import logging
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from handlers import start_command, handle_text, handle_callback_query, faq, list_orders

# Fly.io health-check listener
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
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("✅ Bot is running in POLLING mode...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
