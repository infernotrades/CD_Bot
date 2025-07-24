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
    try:
        with open(log_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [{status.upper()}] {msg}\n")
    except Exception as e:
        logger.error(f"Failed to log order: {e}")

async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(FAQ_TEXT, parse_mode=ParseMode.HTML)

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.effective_chat.id)
    admin_id_str = str(ADMIN_CHAT_ID).lstrip('@')
    if chat_id_str != admin_id_str and update.effective_user.username != "Clones_Direct":
        await update.message.reply_text("❌ Unauthorized.")
        return
    ensure_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM orders WHERE status = 'pending'")
        orders = c.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to list orders: {e}")
        await update.message.reply_text("⚠️ Error accessing orders. Check logs.")
        return
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

# ... (the rest of the code remains the same as in the previous handlers.py, including start_command, get_strain_buttons, send_strain_details, handle_add_quantity, show_confirmation_summary, handle_text, handle_callback_query, show_country_selection, handle_callback_query_from_text)
async def handle_callback_query_from_text(update, action):
    class DummyQuery:
        def __init__(self, msg, data):
            self.message = msg
            self.data = data
        async def answer(self):
            pass
    dummy_query = DummyQuery(update.message, action)
    dummy_update = Update(update.update_id, callback_query=dummy_query)
    await handle_callback_query(dummy_update, None)
