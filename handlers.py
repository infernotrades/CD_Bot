import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import re

with open("strains.json", "r") as f:
    STRAINS = json.load(f)

CART = {}
FAQ_TEXT = """
<b>Frequently Asked Questions</b>

• Orders ship within 14 days of payment unless otherwise stated.
• Worldwide shipping.
• Strains sourced from breeders, seed hunts, or trusted nurseries.
• 7-day satisfaction guarantee.
• 1 free reship allowed (then customer covers shipping).
• All clones are grown in Oasis root cubes.
"""

PRICING_TEXT = """
<b>Pricing:</b>
• 1–2 clones: $80 each
• 3+ clones: $60 each

<b>Shipping:</b>
• USA: $40 (1–2 days)
• International: $100 (3–5 days)

<b>PayPal Fee:</b>
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
    row = []
    for i, s in enumerate(STRAINS):
        row.append(InlineKeyboardButton(s["name"], callback_data=f"strain_{s['name']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons

async def send_strain_details(update: Update, context: ContextTypes.DEFAULT_TYPE, strain_name: str):
    user_id = update.effective_user.id
    strain = next((s for s in STRAINS if s["name"] == strain_name), None)
    if not strain:
        return
    CART[user_id]["last_strain"] = strain_name
    caption = f"<b>{strain['name']}</b>\n{strain['lineage']}\n\n{strain['notes']}\n"
    if strain.get("breeder_url"):
        caption += f"\n<a href='{strain['breeder_url']}'>Breeder Info</a>"
    buttons = [[InlineKeyboardButton("➕ Add to Cart", callback_data="add_quantity")]]
    await update.callback_query.message.reply_photo(
        photo=strain["image_url"],
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_add_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("How many clones would you like to add?\n\n" + PRICING_TEXT)

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

    if "last_strain" in CART[user_id]:
        try:
            qty = int(re.findall(r"\d+", text)[0])
        except IndexError:
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
                [InlineKeyboardButton("🛒 Finalize Order", callback_data="view_cart")],
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

    if data.startswith("strain_"):
        strain_name = data.split("strain_")[1]
        await send_strain_details(update, context, strain_name)
        return

    if data == "view_strains":
        await query.message.reply_text("📋 Select a strain to view details:",
            reply_markup=InlineKeyboardMarkup(get_strain_buttons()))
    elif data == "faq":
        await query.message.reply_text(FAQ_TEXT, parse_mode=ParseMode.HTML)
    elif data == "view_cart":
        if not CART[user_id]["items"]:
            await query.message.reply_text("🛒 Your cart is empty.")
            return
        cart_summary = ""
        for i, item in enumerate(CART[user_id]["items"]):
            cart_summary += f"{i+1}. {item['quantity']}x {item['strain']}\n"
        buttons = [
            [InlineKeyboardButton("✅ Finalize Order", callback_data="finalize_order")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains")]
        ]
        await query.message.reply_text(f"🛒 <b>Your Cart</b>\n\n{cart_summary}", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
    elif data == "finalize_order":
        await query.message.reply_text("💳 Select payment method:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Crypto (BTC/ETH/SOL/USDC)", callback_data="crypto")],
            [InlineKeyboardButton("PayPal (+5% Fee)", callback_data="paypal")]
        ]))
    elif data == "crypto":
        await query.message.reply_text("Please reply with your preferred crypto (e.g., SOL, USDT, etc.)")
    elif data == "paypal":
        await query.message.reply_text("PayPal selected. You'll receive the invoice shortly.")
    elif data == "add_quantity":
        await handle_add_quantity(update, context)

async def handle_callback_query_from_text(update, data):
    class DummyCallbackQuery:
        def __init__(self, update):
            self.message = update.message
            self.data = data
        async def answer(self):
            pass
    dummy_update = Update(update.update_id, callback_query=DummyCallbackQuery(update))
    await handle_callback_query(dummy_update, None)
