import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes


TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🛒 فروشگاه", callback_data="shop")],
        [InlineKeyboardButton("📦 محصولات", callback_data="products")],
        [InlineKeyboardButton("👤 حساب من", callback_data="account")],
        [InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
    ]

    await update.message.reply_text(
        "سلام 👋\n"
        "به فروشگاه ما خوش آمدید.\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "shop":
        await query.edit_message_text(
            "🛒 فروشگاه\n\n"
            "فعلاً محصولات فروشگاه در حال آماده‌سازی است."
        )

    elif query.data == "products":
        await query.edit_message_text(
            "📦 محصولات\n\n"
            "به‌زودی لیست محصولات و اشتراک‌ها اینجا نمایش داده می‌شود."
        )

    elif query.data == "account":
        user = query.from_user
        await query.edit_message_text(
            f"👤 حساب شما\n\n"
            f"نام: {user.first_name}\n"
            f"شناسه کاربری: {user.id}"
        )

    elif query.data == "support":
        await query.edit_message_text(
            "📞 پشتیبانی\n\n"
            "برای ارتباط با پشتیبانی، پیام خود را ارسال کنید."
        )


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
