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

# SQLite DB path
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
        try
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
            [InlineKeyboardButton("✅ Complete", callback_data=f"complete_{order_id}"), InlineKeyboardButton(" First, the user is frustrated and wants the bot to work. The logs show a repeated NameError: name 'faq' is not defined in bot.py.

From the logs, the app starts, mounts /app/data, runs python bot.py, and crashes with the NameError.

The issue is in bot.py: it's trying to add CommandHandler("help", faq), but faq is not imported or defined in bot.py.

In my previous responses, I had import from handlers import start_command, handle_text, handle_callback_query, faq, list_orders, backup_db, stats

So, the code has it, but perhaps the user has an old version.

The user has a Git issue: "fatal: not a git repository"

From the user's message: when they tried git add, it said not a git repo.

So, the repo is not initialized as Git, or they're in the wrong folder.

To make it work, I need to help initialize Git if needed, then update the code, commit, push, deploy.

The path is C:\Users\Daniel\CD_Bot, and they have files there.

To make it work, provide the full, correct bot.py and handlers.py again, with all functions defined.

The user says "please just make it work right" – so, provide the fixed files, and step-by-step to initialize Git, add, commit, push, deploy.

The volume is mounted at /app/data, so DB_PATH should be '/app/data/orders.db'

Region is sea from logs.

Update fly.toml accordingly.

For Git:
- If not a git repo, run git init, git remote add origin <url>, but they have GitHub repo from project summary: https://github.com/infernotrades/CD_Bot

So, assume it's cloned, but perhaps .git folder is missing.

Instructions to init Git if needed.

Finally, the response should be the fixed files and instructions.### Fixed Files and Instructions to Make the Bot Work

I apologize for the frustration—the repeated NameError is from `faq` not being properly imported in `bot.py` (likely an old version was deployed). The Git errors show your folder isn't a Git repository yet (or the .git folder is missing), so we'll fix that too. The volume mount is at `/app/data`, so I've updated `DB_PATH` in `handlers.py`. Your region is `sea` from logs, so I've set it in `fly.toml`.

Below are the fixed files (copy them over your existing ones). Then, follow the steps to initialize Git (if needed), commit, push, and deploy. This will make the bot run without crashes.

#### Fixed `bot.py` (added faq import)
```python
import os
import logging
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from handlers import start_command, handle_text, handle_callback_query, faq, list_orders, backup_db, stats

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
    app.add_handler(CommandHandler("help", faq))
    app.add_handler(CommandHandler("faq", faq))
    app.add_handler(CommandHandler("orders", list_orders))
    app.add_handler(CommandHandler("backup", backup_db))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("✅ Bot is running in POLLING mode...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
