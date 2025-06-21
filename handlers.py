from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from strain_data import get_strain_by_name, STRAIN_NAMES

# In-memory user carts and temp state
USER_CARTS = {}
USER_STATE = {}

STRAIN_NAMES.sort()

def build_keyboard():
    keyboard = []
    row = []
    for i, name in enumerate(STRAIN_NAMES):
        row.append(InlineKeyboardButton(name, callback_data=name))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("🛒 View Cart", callback_data="view_cart"),
        InlineKeyboardButton("✅ Finalize Order", callback_data="finalize_order")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_post_add_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu"),
         InlineKeyboardButton("✅ Finalize Order", callback_data="finalize_order")]
    ])

def get_cart_markup(name):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add to Order", callback_data=f"add_to_cart|{name}")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
    ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Welcome, {update.effective_user.first_name}! Let’s get started.\n\n"
        "🌿 Choose a strain to learn more:",
        reply_markup=build_keyboard()
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in USER_STATE and USER_STATE[user_id].get("awaiting_quantity"):
        strain_name = USER_STATE[user_id]["strain"]
        try:
            quantity = int(update.message.text.strip())
            cart = USER_CARTS.setdefault(user_id, {})
            cart[strain_name] = cart.get(strain_name, 0) + quantity
            USER_STATE[user_id]["awaiting_quantity"] = False

            await update.message.reply_text(
                f"✅ Added {quantity}x {strain_name} to your cart.",
                reply_markup=get_post_add_markup()
            )
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number.")
        return

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "back_to_menu":
        await query.message.edit_text(
            "🌿 Choose a strain to learn more:",
            reply_markup=build_keyboard()
        )
        return

    if data == "view_cart":
        cart = USER_CARTS.get(user_id, {})
        if not cart:
            await query.message.reply_text("🛒 Your cart is empty.")
        else:
            cart_text = "\n".join(f"• {k} x{v}" for k, v in cart.items())
            await query.message.reply_text(f"🛒 Your cart:\n{cart_text}", reply_markup=get_post_add_markup())
        return

    if data == "finalize_order":
        cart = USER_CARTS.get(user_id, {})
        if not cart:
            await query.message.reply_text("🛒 Your cart is empty.")
        else:
            cart_text = "\n".join(f"• {k} x{v}" for k, v in cart.items())
            await query.message.reply_text(
                f"📝 Review your order:\n{cart_text}\n\n🚀 Coming soon: Checkout flow.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
                ])
            )
        return

    if data.startswith("add_to_cart|"):
        _, strain_name = data.split("|", 1)
        USER_STATE[user_id] = {"awaiting_quantity": True, "strain": strain_name}
        await query.message.reply_text(f"🌱 How many clones of {strain_name} would you like to add?")
        return

    # Show strain info
    strain = get_strain_by_name(data)
    if not strain:
        await query.edit_message_text("❌ Strain not found.")
        return

    breeder = strain.get("breeder", "Unknown")
    breeder_url = strain.get("breeder_url")
    notes = strain.get("notes", "")
    image_url = strain.get("image_url", "https://i.imgur.com/hN9uz7I.png")

    caption = (
        f"<b>{strain['name']}</b>\n"
        f"🧬 <b>Lineage:</b> {strain.get('lineage', 'Unknown')}\n"
    )
    if breeder_url:
        caption += f"🌱 <b>Breeder:</b> <a href='{breeder_url}'>{breeder}</a>\n"
    else:
        caption += f"🌱 <b>Breeder:</b> {breeder}\n"
    if notes:
        caption += f"📝 <b>Notes:</b> {notes}"

    try:
        await query.edit_message_media(
            media=InputMediaPhoto(
                media=image_url,
                caption=caption,
                parse_mode="HTML"
            ),
            reply_markup=get_cart_markup(strain["name"])
        )
    except Exception as e:
        print(f"[Error] Failed to send image: {e}")
        await query.edit_message_text(
            caption or "Strain info unavailable.",
            parse_mode="HTML",
            reply_markup=get_cart_markup(strain["name"])
        )
