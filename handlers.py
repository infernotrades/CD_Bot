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

# Load strain data
with open("strains.json", "r") as f:
    STRAINS = json.load(f)

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
    total_clones = sum(item['quantity'] for item in items)
    clone_price = 60 if total_clones >= 3 else 80
    base_total = total_clones * clone_price
    shipping = 100 if country.lower() != "usa" else 40
    fee = 0.05 * (base_total + shipping) if payment_method == "PayPal" else 0
    return base_total + shipping + fee

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    CART[user_id] = {"items": []}
    buttons = [
        [InlineKeyboardButton("📋 View Strains", callback_data="view_strains")],
        [InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")],
        [InlineKeyboardButton("❓ FAQ", callback_data="faq")]
    ]
    await update.message.reply_text(
        "Welcome to Clone Direct! 🌱👋 Browse elite clones and build your custom order below.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def slugify(name: str) -> str:
    # Replace spaces and special chars for callback_data
    return re.sub(r"[^a-zA-Z0-9_]+", "_", name.replace(' ', '_'))

def get_strain_buttons():
    buttons = []
    for i in range(0, len(STRAINS), 2):
        row = []
        for j in range(2):
            if i + j < len(STRAINS):
                s = STRAINS[i + j]
                slug = slugify(s['name'])
                row.append(InlineKeyboardButton(s["name"], callback_data=f"strain_{slug}"))
        buttons.append(row)
    return buttons

async def send_strain_details(update: Update, context: ContextTypes.DEFAULT_TYPE, slug: str):
    # Convert slug back to name
    name = slug.replace('_', ' ')
    strain = next((s for s in STRAINS if s["name"] == name), None)
    if not strain:
        logger.error(f"Strain not found for slug: {slug}")
        return

    user_id = update.effective_user.id
    CART[user_id]["last_strain"] = strain["name"]

    caption = (
        f"*{strain['name']}*\n"
        f"_Genetics:_ {strain['lineage']}\n"
        f"_Breeder:_ {strain.get('breeder','Unknown')}\n\n"
        f"{strain.get('notes','')}"
    )
    if strain.get("breeder_url"):
        caption += f"\n\n[Breeder Info]({strain['breeder_url']})"

    buttons = [[
        InlineKeyboardButton("➕ Add to Cart", callback_data="add_quantity"),
        InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains")
    ]]

    await update.callback_query.message.reply_photo(
        photo=strain["image_url"],
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_add_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text(
        "How many clones would you like to add?\n\n" + PRICING_TEXT
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Processing 'other' crypto input
    if user_id in CART and CART[user_id].get('awaiting_crypto_other'):
        CART[user_id]['payment_method'] = text
        del CART[user_id]['awaiting_crypto_other']
        await update.message.reply_text("Please enter your Instagram handle (e.g., @username)")
        return

    # Awaiting IG handle
    if user_id in CART and CART[user_id].get('payment_method') and 'ig_handle' not in CART[user_id]:
        CART[user_id]['ig_handle'] = text
        await update.message.reply_text(
            "👍 Thanks! I’ve sent your order for processing. We’ll reach out shortly."
        )
        items = CART[user_id]['items']
        order_lines = [f"- {it['strain']} x{it['quantity']}" for it in items]
        order_info = (
            f"📦 New order from IG {text}:\n"
            f"Payment Method: {CART[user_id]['payment_method']}\n"
            f"Items:\n" + "\n".join(order_lines)
        )
        chat_id = ADMIN_CHAT_ID
        if chat_id.lstrip('-').isdigit():
            chat_id = int(chat_id)
        try:
            await context.bot.send_message(chat_id=chat_id, text=order_info)
            logger.info("✅ Order DM sent to admin chat")
        except Exception as e:
            logger.error(f"❌ Failed to send order DM: {e}")
        del CART[user_id]
        return

    if user_id not in CART:
        CART[user_id] = {"items": []}

    # Main menu triggers
    for key, action in {"clones":"view_strains","strains":"view_strains","menu":"view_strains","how much":"faq","faq":"faq"}.items():
        if key in text.lower():
            await handle_callback_query_from_text(update, action)
            return

    # Quantity input
    if 'last_strain' in CART[user_id]:
        nums = re.findall(r"\d+", text)
        if not nums:
            await update.message.reply_text("Please enter a valid number.")
            return
        qty = int(nums[0])
        CART[user_id]['items'].append({'strain': CART[user_id]['last_strain'], 'quantity': qty})
        del CART[user_id]['last_strain']
        await update.message.reply_text(
            f"✅ Added {CART[user_id]['items'][-1]['strain']} x{qty} to your cart.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains")]
            ])
        )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data
    logger.info(f"Callback data received: {data}")

    if user_id not in CART:
        CART[user_id] = {"items": []}

    if data.startswith("strain_"):
        slug = data.split("strain_", 1)[1]
        await send_strain_details(update, context, slug)
        return

    if data == "view_strains":
        await query.message.reply_text(
            "📋 Select a strain to view details:",
            reply_markup=InlineKeyboardMarkup(get_strain_buttons())
        )
    elif data == "faq":
        await query.message.reply_text(FAQ_TEXT)
    elif data == "view_cart":
        items = CART[user_id]["items"]
        if not items:
            await query.message.reply_text("🛒 Your cart is empty.")
            return
        summary = "\n".join(f"{i+1}. {it['strain']} x{it['quantity']}" for i, it in enumerate(items))
        await query.message.reply_text(
            f"🛒 *Your Cart*\n\n{summary}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Finalize Order", callback_data="finalize_order")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains")]
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
    elif data == "crypto":
        await query.message.reply_text(
            "Select crypto:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Bitcoin (BTC)", callback_data="pay_btc")],
                [InlineKeyboardButton("Ethereum (ETH)", callback_data="pay_eth")],
                [InlineKeyboardButton("Solana (SOL)", callback_data="pay_sol")],
                [InlineKeyboardButton("USDC", callback_data="pay_usdc")],
                [InlineKeyboardButton("USDT", callback_data="pay_usdt")],
                [InlineKeyboardButton("Other", callback_data="crypto_other")]
            ])
        )
    elif data in ("pay_btc","pay_eth","pay_sol","pay_usdc","pay_usdt"):
        mapping = {
            'pay_btc':'Bitcoin (BTC)', 'pay_eth':'Ethereum (ETH)', 'pay_sol':'Solana (SOL)',
            'pay_usdc':'USDC', 'pay_usdt':'USDT'
        }
        CART[user_id]['payment_method'] = mapping[data]
        await query.message.reply_text("Please enter your Instagram handle (e.g., @username)")
    elif data == "crypto_other":
        CART[user_id]['awaiting_crypto_other'] = True
        await query.message.reply_text("Please enter your preferred crypto (e.g., SOL, USDT, etc.)")
    elif data == "paypal":
        CART[user_id]['payment_method'] = "PayPal"
        await query.message.reply_text("Please enter your Instagram handle (e.g., @username)")
    elif data == "mail_in":
        CART[user_id]['payment_method'] = "Mail In"
        await query.message.reply_text("Please enter your Instagram handle (e.g., @username)")
    elif data == "add_quantity":
        await handle_add_quantity(update, context)

async def handle_callback_query_from_text(update, data):
    class DummyCQ:
        def __init__(self, update, data):
            self.message = update.message
            self.data = data
        async def answer(self):
            pass
    await handle_callback_query(Update(update.update_id, callback_query=DummyCQ(update, data)), None)
