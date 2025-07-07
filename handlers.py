import json
import re
import urllib.parse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Load strain data
with open("strains.json", "r") as f:
    STRAINS = json.load(f)

# In-memory cart/state
CART = {}

# FAQ & pricing text
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
        "Welcome to Clone Direct! 🌱👋 Browse elite clones and build your custom order below.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

def get_strain_buttons():
    buttons = []
    for i in range(0, len(STRAINS), 2):
        row = []
        for j in (0, 1):
            if i+j < len(STRAINS):
                s = STRAINS[i+j]
                # URL-encode the name so callback_data is safe
                token = urllib.parse.quote(s["name"])
                row.append(InlineKeyboardButton(
                    s["name"],
                    callback_data=f"strain_{token}"
                ))
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

    # 1) after payment method → collect IG handle
    if uid in CART and CART[uid].get("payment_method") and "ig_handle" not in CART[uid]:
        CART[uid]["ig_handle"] = text
        # send confirmation
        await update.message.reply_text(
            "👍 Thanks! I’ve sent your order for processing. We’ll reach out shortly."
        )
        # build DM to admin
        items = CART[uid]["items"]
        order_lines = "\n".join(f"- {it['strain']} x{it['quantity']}" for it in items)
        order_info = (
            f"📦 *New Order*\n"
            f"• From: `{update.effective_user.username}`\n"
            f"• IG: {text}\n"
            f"• Payment: {CART[uid]['payment_method']}\n"
            f"• Items:\n{order_lines}"
        )
        # DM to admin channel
        await context.bot.send_message(
            chat_id= int(os.getenv("ADMIN_CHAT_ID")),
            text=order_info,
            parse_mode=ParseMode.MARKDOWN
        )
        # clear
        del CART[uid]
        return

    # 2) Smart keyword shortcuts
    if uid not in CART:
        CART[uid] = {"items": []}
    for key, action in {
        "clones":"view_strains","strains":"view_strains","menu":"view_strains",
        "how much":"faq","faq":"faq"
    }.items():
        if key in text.lower():
            await handle_callback_query_from_text(update, action)
            return

    # 3) quantity entry
    if uid in CART and "last_strain" in CART[uid]:
        match = re.findall(r"\d+", text)
        if not match:
            await update.message.reply_text("Please enter a valid number.")
            return
        qty = int(match[0])
        CART[uid]["items"].append({
            "strain": CART[uid]["last_strain"],
            "quantity": qty
        })
        del CART[uid]["last_strain"]
        await update.message.reply_text(
            f"✅ Added {CART[uid]['items'][-1]['strain']} x{qty} to your cart.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="view_strains")],
            ])
        )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    uid  = update.effective_user.id
    data = update.callback_query.data

    if uid not in CART:
        CART[uid] = {"items": []}

    # 1) strain details
    if data.startswith("strain_"):
        token = data[len("strain_"):]
        name  = urllib.parse.unquote(token)
        await send_strain_details(update, context, name)
        return

    # 2) view strains
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
        summary = "\n".join(f"{i+1}. {it['strain']} x{it['quantity']}"
                            for i,it in enumerate(items))
        await update.callback_query.message.reply_text(
            f"🛒 *Your Cart*\n\n{summary}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Finalize Order", callback_data="finalize_order")],
                [InlineKeyboardButton("🔙 Back to Menu",    callback_data="view_strains")],
            ])
        )
    elif data == "finalize_order":
        await update.callback_query.message.reply_text(
            "💳 Select payment method:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Crypto", callback_data="crypto")],
                [InlineKeyboardButton("💳 PayPal", callback_data="paypal")],
                [InlineKeyboardButton("✉️ Mail In", callback_data="mail_in")],
            ])
        )
    elif data in ("crypto","paypal","mail_in"):
        labels = {"crypto":"Crypto","paypal":"PayPal","mail_in":"Mail In"}
        CART[uid]["payment_method"] = labels[data]
        await update.callback_query.message.reply_text(
            "Please enter your Instagram handle (e.g., @username)"
        )
    elif data == "add_quantity":
        await handle_add_quantity(update, context)

async def handle_callback_query_from_text(update, data):
    class DummyCQ:
        def __init__(self, msg, d): self.message, self.data = msg, d
        async def answer(self): pass
    dummy = DummyCQ(update.message, data)
    from telegram import Update as U
    await handle_callback_query(U(update.update_id, callback_query=dummy), None)
