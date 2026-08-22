import os
import psycopg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
def init_db():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()
async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("🛒 فروشگاه", callback_data="shop")],
        [InlineKeyboardButton("📦 محصولات", callback_data="products")],
        [InlineKeyboardButton("👤 حساب من", callback_data="account")],
        [InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
    ]

    await update.message.reply_text(
        "سلام 👋\n"
        "به فروشگاه ما خوش آمدید.\n\n"
        "لطفاً یک گزینه را انتخاب کنید:",
     
        reply_markup=InlineKeyboardMarkup(keyboard),

        async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "shop":
        keyboard = [
            [InlineKeyboardButton("📱 تلگرام پریمیوم", callback_data="telegram")],
            [InlineKeyboardButton("🔐 اکانت‌ها", callback_data="accounts")],
            [InlineKeyboardButton("🌐 کانفیگ VPN", callback_data="vpn")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back")],
        ]

        await query.edit_message_text(
            "🛒 فروشگاه\n\n"
            "لطفاً دسته‌بندی موردنظر را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "products":
        keyboard = [
            [InlineKeyboardButton("📱 تلگرام پریمیوم", callback_data="telegram")],
            [InlineKeyboardButton("🔐 اکانت‌ها", callback_data="accounts")],
            [InlineKeyboardButton("🌐 کانفیگ VPN", callback_data="vpn")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back")],
        ]

        await query.edit_message_text(
            "📦 محصولات\n\n"
            "دسته‌بندی محصولات را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "telegram":
        await query.edit_message_text(
            "📱 تلگرام پریمیوم\n\n"
            "محصولات تلگرام پریمیوم به‌زودی اضافه می‌شوند."
        )

    elif query.data == "accounts":
        await query.edit_message_text(
            "🔐 اکانت‌ها\n\n"
            "لیست اکانت‌های موجود به‌زودی اضافه می‌شود."
        )

    elif query.data == "vpn":
        await query.edit_message_text(
            "🌐 کانفیگ VPN\n\n"
            "کانفیگ‌های موجود به‌زودی اضافه می‌شوند."
        )

    elif query.data == "account":
        user = query.from_user

        text = (
            "👤 حساب شما\n\n"
            f"نام: {user.first_name}\n"
            f"شناسه: {user.id}"
        )

        await query.edit_message_text(text)

    elif query.data == "support":
        await query.edit_message_text(
            "📞 پشتیبانی\n\n"
            "برای ارتباط با پشتیبانی پیام خود را ارسال کنید."
        )

    elif query.data == "back":
        keyboard = [
            [InlineKeyboardButton("🛒 فروشگاه", callback_data="shop")],
            [InlineKeyboardButton("📦 محصولات", callback_data="products")],
            [InlineKeyboardButton("👤 حساب من", callback_data="account")],
            [InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
        ]

        await query.edit_message_text(
            "👋 سلام\n\n"
            "به فروشگاه ما خوش آمدید.\n\n"
            "لطفاً یک گزینه را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    else:
        await query.edit_message_text("❌ گزینه نامعتبر است.")
    if not TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    if not RENDER_URL:
        raise ValueError("RENDER_EXTERNAL_URL is not set")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="telegram",
        webhook_url=f"{RENDER_URL}/telegram",
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
