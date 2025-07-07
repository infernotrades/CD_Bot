import os
import json
import re
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Setup logger
logger = logging.getLogger(__name__)

# Admin chat ID (numeric or @handle)
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "@clones_direct")

# Load and sort strain data alphabetically by name
with open("strains.json", "r") as f:
    data = json.load(f)
STRAINS = sorted(data, key=lambda s: s["name"].lower())

# In-memory cart storage
CART = {}

# Plain-text FAQ and pricing
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

def calculate_price(items, country, payment_method):
    total_clones = sum(item["quantity"] for item in items)
    clone_price = 60 if total_clones >= 3 else 80
    base_total = total_clones * clone_price
    shipping = 40 if country.lower() == "usa" else 100
    fee = 0.05 * (base_total + shipping) if payment_method == "PayPal" else 0
    return base_total + shipping + fee

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    CART[user_id] = {"items": []}
    buttons = [
        [InlineKeyboardButton("📋 View Strains", callback_data="view_strains")],
        [InlineKeyboardButton("🛒 View Cart",    callback_data="view_cart")],
        [InlineKeyboardButton("❓ FAQ",          callback_data="faq")],
    ]
    await update.message.reply_text(
        "Welcome to Clones Direct! 🌱👋 Browse elite clones and build your custom order below.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

def get_strain_buttons():
    buttons = []
    for i in range(0, len(STRAINS), 2):
        row = []
        for j in range(2):
            idx = i + j
            if idx < len(STRAINS):
                name = STRAINS[idx]["name"]
                row.append(InlineKeyboardButton(name, callback_data=f"strain_{idx}"))
        buttons.append(row)
    return buttons

async def send_strain_details(update: Update, context: ContextTypes.DEFAULT_TYPE, strain_name: str):
    strain = next((s for s in STRAINS if s["name"] == strain_name), None)
    if not strain:
        await update.callback_query.message.reply_text("❌ Strain not found.")
        return

    uid = update.effective_user.id
    CART[uid]["last_strain"] = strain_name

    caption = (
        f"*{strain['name']}*\n"
        f"_Genetics:_ {strain['lineage']}\n"
        f"_Breeder:_ {strain.get('breeder','Unknown')}\n\n"
        f"{strain.get('notes','')}"
    )
    if strain.get("breeder_url"):
        caption += f"\n\n[Breeder Info]({strain['breeder_url']})"

    buttons = [
        [
            InlineKeyboardButton("➕ Add to Cart", callback_data="add_quantity"),
            InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains"),
        ]
    ]
    await update.callback_query.message.reply_photo(
        photo=strain["image_url"],
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def handle_add_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("How many clones would you like to add?\n\n" + PRICING_TEXT)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # After payment method → collect IG handle
    if uid in CART and CART[uid].get("payment_method") and "ig_handle" not in CART[uid]:
        CART[uid]["ig_handle"] = text
        await update.message.reply_text("👍 Thanks! I’ve sent your order for processing. We’ll reach out shortly.")

        items = CART[uid]["items"]
        order_lines = "\n".join(f"- {it['strain']} x{it['quantity']}" for it in items)
        user = update.effective_user
        username = f"@{user.username}" if user.username else f"{user.first_name}"
        order_info = (
            f"📦 *New Order*\n"
            f"• Telegram: {username}\n"
            f"• IG: {text}\n"
            f"• Payment: {CART[uid]['payment_method']}\n"
            f"• Items:\n{order_lines}"
        )
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=order_info,
            parse_mode=ParseMode.MARKDOWN
        )
        del CART[uid]
        return

    # Ensure cart exists
    if uid not in CART:
        CART[uid] = {"items": []}

    # Smart menu keywords
    for key, action in {
        "clones":"view_strains","strains":"view_strains","menu":"view_strains",
        "how much":"faq","faq":"faq"
    }.items():
        if key in text.lower():
            await handle_callback_query_from_text(update, action)
            return

    # Quantity entry
    if "last_strain" in CART[uid]:
        nums = re.findall(r"\d+", text)
        if not nums:
            await update.message.reply_text("Please enter a valid number.")
            return
        qty = int(nums[0])
        CART[uid]["items"].append({"strain": CART[uid]["last_strain"], "quantity": qty})
        del CART[uid]["last_strain"]
        await update.message.reply_text(
            f"✅ Added {CART[uid]['items'][-1]['strain']} x{qty} to your cart.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains")],
            ])
        )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid  = update.effective_user.id

    if uid not in CART:
        CART[uid] = {"items": []}

    # strain_{idx}
    if data.startswith("strain_"):
        idx = int(data.split("_", 1)[1])
        strain_name = STRAINS[idx]["name"]
        await send_strain_details(update, context, strain_name)
        return

    if data == "view_strains":
        await query.message.reply_text(
            "📋 Select a strain to view details:",
            reply_markup=InlineKeyboardMarkup(get_strain_buttons())
        )
    elif data == "faq":
        await query.message.reply_text(FAQ_TEXT)
    elif data == "view_cart":
        items = CART[uid]["items"]
        if not items:
            await query.message.reply_text("🛒 Your cart is empty.")
            return
        summary = "\n".join(f"{i+1}. {it['strain']} x{it['quantity']}" for i, it in enumerate(items))
        await query.message.reply_text(
            f"🛒 *Your Cart*\n\n{summary}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Finalize Order", callback_data="finalize_order")],
                [InlineKeyboardButton("🔙 Back to Menu",   callback_data="view_strains")]
            ])
        )
    elif data == "finalize_order":
        await query.message.reply_text(
            "💳 Select payment method:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Crypto", callback_data="crypto")],
                [InlineKeyboardButton("💳 PayPal", callback_data="paypal")],
                [InlineKeyboardButton("✉️ Mail In", callback_data="mail_in")]
            ])
        )
    elif data in ("crypto","paypal","mail_in"):
        CART[uid]["payment_method"] = {"crypto":"Crypto","paypal":"PayPal","mail_in":"Mail In"}[data]
        await query.message.reply_text("Please enter your Instagram handle (e.g., @username)")
    elif data == "add_quantity":
        await handle_add_quantity(update, context)

async def handle_callback_query_from_text(update, data):
    class DummyCQ:
        def __init__(self, u, d): self.message, self.data = u.message, d
        async def answer(self): pass
    from telegram import Update as U
    await handle_callback_query(U(update.update_id, callback_query=DummyCQ(update, data)), None)