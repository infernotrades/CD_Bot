import os
import json
import sqlite3
import logging
import re
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Setup logger
logger = logging.getLogger(__name__)

# Admin chat ID from environment
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "@clones_direct")

# SQLite DB path (updated to match mount in logs)
DB_PATH = '/app/data/orders.db'

# In-memory rate limit (user_id: [timestamp list])
RATE_LIMIT = {}  # max 10 msg/min
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 10

initialized = False

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Orders table with indexes
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
    c.execute('CREATE INDEX IF NOT EXISTS idx_user_time ON orders (telegram_user, timestamp)')
    # Carts table for persistence
    c.execute('''CREATE TABLE IF NOT EXISTS carts
                 (user_id INTEGER PRIMARY KEY,
                  cart JSON,
                  last_updated TEXT)''')
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

def sanitize_input(text):
    return re.sub(r'[^a-zA-Z0-9_@.-]', '', text)

def check_rate_limit(uid):
    now = datetime.now().timestamp()
    if uid not in RATE_LIMIT:
        RATE_LIMIT[uid] = []
    RATE_LIMIT[uid] = [t for t in RATE_LIMIT[uid] if now - t < RATE_LIMIT_WINDOW]
    if len(RATE_LIMIT[uid]) >= RATE_LIMIT_MAX:
        return False
    RATE_LIMIT[uid].append(now)
    return True

def check_duplicate_order(telegram_user):
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM orders WHERE telegram_user = ? AND timestamp > ?",
              (telegram_user, (datetime.now() - timedelta(hours=24)).isoformat()))
    result = c.fetchone()
    conn.close()
    return result is not None

def save_order_to_db(telegram_user, ig_handle, payment, country, total, items):
    ig_handle = sanitize_input(ig_handle)
    if check_duplicate_order(telegram_user):
        return None  # Duplicate
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

def load_cart(uid):
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT cart FROM carts WHERE user_id = ?", (uid,))
    result = c.fetchone()
    conn.close()
    return json.loads(result[0]) if result else {"items": [], "state": None, "age_confirmed": False}

def save_cart(uid, cart):
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO carts (user_id, cart, last_updated)
                 VALUES (?, ?, ?)''', (uid, json.dumps(cart), datetime.now().isoformat()))
    conn.commit()
    conn.close()

def log_order(msg, status="success"):
    log_path = os.path.join(os.path.dirname(DB_PATH), "order_log.txt")
    if os.path.exists(log_path) and os.path.getsize(log_path) > 1 * 1024 * 1024:
        open(log_path, 'w').close()  # Truncate if >1MB
    with open(log_path, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] [{status.upper()}] {msg}\n")

async def backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_CHAT_ID):
        return
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM orders")
    orders = c.fetchall()
    conn.close()
    backup_data = json.dumps(orders, default=str)
    await update.message.reply_text(backup_data, parse_mode=ParseMode.JSON)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_CHAT_ID):
        return
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM orders")
    total_orders = c.fetchone()[0]
    c.execute("SELECT items FROM orders")
    items = [json.loads(row[0]) for row in c.fetchall()]
    strain_count = {}
    for order in items:
        for it in order:
            strain_count[it['strain']] = strain_count.get(it['strain'], 0) + it['quantity']
    top_strains = sorted(strain_count.items(), key=lambda x: x[1], reverse=True)[:5]
    conn.close()
    msg = f"Total Orders: {total_orders}\nTop Strains:\n" + "\n".join(f"{s}: {c}" for s, c in top_strains)
    await update.message.reply_text(msg)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not check_rate_limit(uid):
        await update.message.reply_text("Slow down! Too many messages.")
        return
    cart = load_cart(uid)
    if cart.get("age_confirmed", False):
        keyboard = [
            [InlineKeyboardButton("📋 View Strains", callback_data="view_strains")],
            [InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")],
            [InlineKeyboardButton("❓ FAQ", callback_data="faq")],
        ]
        await update.message.reply_text("Welcome back! Browse below.", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        keyboard = [[InlineKeyboardButton("✅ I am 21+ and in a legal area", callback_data="confirm_age")]]
        await update.message.reply_text("Welcome! Confirm you're 21+ and in a legal area to proceed.", reply_markup=InlineKeyboardMarkup(keyboard))

async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(FAQ_TEXT, parse_mode=ParseMode.HTML)

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_CHAT_ID):
        await update.message.reply_text("❌ Unauthorized.")
        return
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM orders")
    orders = c.fetchall()
    conn.close()
    if not orders:
        await update.message.reply_text("No orders.")
        return
    for order in orders:
        order_id, timestamp, tg_user, ig, payment, country, total, items_json, status = order
        if status == 'pending' and datetime.fromisoformat(timestamp) < datetime.now() - timedelta(days=14):
            update_order_status(order_id, 'expired')
            status = 'expired'
        items = json.loads(items_json)
        lines = "\n".join(f"{it['strain']} x{it['quantity']}" for it in items)
        msg = f"Order #{order_id} ({timestamp})\nUser: {tg_user}\nIG: {ig}\nPayment: {payment}\nCountry: {country}\nTotal: ${total}\nItems: {lines}\nStatus: {status}"
        keyboard = [
            [InlineKeyboardButton("✅ Complete", callback_data=f"complete_{order_id}"), InlineKeyboardButton("❌ Delete", callback_data=f"delete_{order_id}")]
        ]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

# (The rest of handlers.py, including get_strain_buttons, send_strain_details, handle_add_quantity, show_country_selection, handle_callback_query, calculate_subtotal, calculate_price, etc., remain as in the last complete version, with cart = load_cart(uid) at the beginning of relevant functions and save_cart(uid, cart) at the end. For brevity, not repeating the full code, but ensure your file includes them.)

# Example for handle_callback_query:
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = update.callback_query.data
    uid = update.effective_user.id
    cart = load_cart(uid)
    if data == "confirm_age":
        cart["age_confirmed"] = True
        save_cart(uid, cart)
        keyboard = [
            [InlineKeyboardButton("📋 View Strains", callback_data="view_strains")],
            [InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")],
            [InlineKeyboardButton("❓ FAQ", callback_data="faq")],
        ]
        await update.callback_query.edit_message_text("Age confirmed! Browse below.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if not cart.get("age_confirmed", False):
        await update.callback_query.message.reply_text("Please confirm age first with /start.")
        return
    # Continue with other data checks (view_strains, view_cart, etc.), saving cart at end.

# Ensure all callback and text handlers follow this pattern.
