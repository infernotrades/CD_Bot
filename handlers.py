import json
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Load strain data
with open("strains.json", "r") as f:
    STRAINS = json.load(f)

# Simple in-memory cart
CART = {}

# FAQ and pricing (plain text)
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
    fee = 0.05 * (base_total + shipping) if payment_method == "paypal" else 0
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
        reply_markup=InlineKeyboardMarkup(buttons),
    )

def get_strain_buttons():
    buttons = []
    for i in range(0, len(STRAINS), 2):
        row = []
        for j in range(2):
            if i + j < len(STRAINS):
                s = STRAINS[i + j]
                row.append(
                    InlineKeyboardButton(s["name"], callback_data=f"strain_{s['name']}")
                )
        buttons.append(row)
    return buttons

async def send_strain_details(update: Update, context: ContextTypes.DEFAULT_TYPE, strain_name: str):
    strain = next((s for s in STRAINS if s["name"] == strain_name), None)
    if not strain:
        return

    user_id = update.effective_user.id
    CART[user_id]["last_strain"] = strain_name

    # Build a Markdown caption with full details
    caption = (
        f"*{strain['name']}*\n"
        f"_Genetics:_ {strain['lineage']}\n"
        f"_Breeder:_ {strain.get('breeder', 'Unknown')}\n\n"
        f"{strain.get('notes', '')}"
    )
    if strain.get("breeder_url"):
        caption += f"\n\n[Breeder Info]({strain['breeder_url']})"

    # Two-button row: Add to Cart + Back to Menu
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
    await update.callback_query.message.reply_text(
        "How many clones would you like to add?\n\n" + PRICING_TEXT
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()
    if user_id not in CART:
        CART[user_id] = {"items": []}

    # Smart triggers
    keywords = {
        "clones": "view_strains",
        "strains": "view_strains",
        "menu": "view_strains",
        "how much": "faq",
        "faq": "faq"
    }
    for key, action in keywords.items():
        if key in text:
            await handle_callback_query_from_text(update, action)
            return

    # Quantity entry
    if "last_strain" in CART[user_id]:
        try:
            qty = int(re.findall(r"\d+", text)[0])
        except (IndexError, ValueError):
            await update.message.reply_text("Please enter a valid number.")
            return
        CART[user_id]["items"].append({
            "strain": CART[user_id]["last_strain"],
            "quantity": qty
        })
        del CART[user_id]["last_strain"]
        await update.message.reply_text(
            f"✅ Added {qty}x {CART[user_id]['items'][-1]['strain']} to your cart.",
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

    if user_id not in CART:
        CART[user_id] = {"items": []}

    # Strain selection
    if data.startswith("strain_"):
        strain_name = data.split("strain_", 1)[1]
        await send_strain_details(update, context, strain_name)
        return

    # Main menu flows
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
        cart_summary = "\n".join(
            f"{i+1}. {item['quantity']}x {item['strain']}"
            for i, item in enumerate(items)
        )
        await query.message.reply_text(
            f"🛒 *Your Cart*\n\n{cart_summary}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Finalize Order", callback_data="finalize_order")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains")]
            ])
        )

    # Payment selection
    elif data == "finalize_order":
        await query.message.reply_text(
            "💳 Select payment method:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Crypto", callback_data="crypto")],
                [InlineKeyboardButton("💳 PayPal (+5% Fee)", callback_data="paypal")],
                [InlineKeyboardButton("✉️ Mail In", callback_data="mail_in")],
            ])
        )

    elif data == "crypto":
        await query.message.reply_text(
            "Select your crypto:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Bitcoin (BTC)", callback_data="coin_BTC")],
                [InlineKeyboardButton("Ethereum (ETH)", callback_data="coin_ETH")],
                [InlineKeyboardButton("Solana (SOL)", callback_data="coin_SOL")],
                [InlineKeyboardButton("USDC", callback_data="coin_USDC")],
                [InlineKeyboardButton("USDT", callback_data="coin_USDT")],
                [InlineKeyboardButton("Other", callback_data="coin_OTHER")],
            ])
        )

    elif data.startswith("coin_"):
        coin = data.split("coin_", 1)[1]
        if coin == "OTHER":
            await query.message.reply_text("Please type your preferred crypto:")
        else:
            await query.message.reply_text(
                f"You chose *{coin}*. Please send payment to our {coin} address: `YOUR_{coin}_ADDRESS_HERE`",
                parse_mode=ParseMode.MARKDOWN
            )

    elif data == "paypal":
        await query.message.reply_text("PayPal selected. You’ll receive an invoice shortly.")

    elif data == "mail_in":
        await query.message.reply_text(
            "Mail-In selected. Please send a check or money order to:\n\n"
            "Clones Direct\n123 Greenway Blvd\nGrowtown, CA 90000"
        )

    # Quantity flow
    elif data == "add_quantity":
        await handle_add_quantity(update, context)

async def handle_callback_query_from_text(update, data):
    # Convert text commands into callback flow
    class DummyCallbackQuery:
        def __init__(self, update, data):
            self.message = update.message
            self.data = data
        async def answer(self):
            pass

    dummy_update = Update(update.update_id, callback_query=DummyCallbackQuery(update, data))
    await handle_callback_query(dummy_update, None)
