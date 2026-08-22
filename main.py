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
    )


async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "shop":
        text = "🛒 فروشگاه\n\nمحصولات فروشگاه به‌زودی اضافه می‌شوند."

    elif query.data == "products":
        text = "📦 محصولات\n\nلیست اشتراک‌ها و اکانت‌ها به‌زودی اینجا نمایش داده می‌شود."

    elif query.data == "account":
        user = query.from_user
        text = (
            f"👤 حساب شما\n\n"
            f"نام: {user.first_name}\n"
            f"شناسه: {user.id}"
        )

    elif query.data == "support":
        text = "📞 پشتیبانی\n\nپیام خود را برای پشتیبانی ارسال کنید."

    else:
        text = "گزینه نامعتبر است."

    await query.edit_message_text(text)


def main():
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
