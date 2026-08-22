import os
import psycopg

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)


TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = os.getenv("ADMIN_ID")


# =========================================================
# DATABASE
# =========================================================

def get_db():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set")

    return psycopg.connect(DATABASE_URL)


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    price BIGINT NOT NULL DEFAULT 0,
                    stock INTEGER NOT NULL DEFAULT 0,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    UNIQUE(category, duration)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    product_id INTEGER NOT NULL,
                    price BIGINT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Telegram Premium
            for duration in [1, 3, 6, 12]:
                cur.execute("""
                    INSERT INTO products
                    (category, name, duration, price, stock)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (category, duration) DO NOTHING
                """, (
                    "telegram",
                    "تلگرام پریمیوم",
                    duration,
                    0,
                    0
                ))

            # VPN
            for duration in [1, 3, 6, 12]:
                cur.execute("""
                    INSERT INTO products
                    (category, name, duration, price, stock)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (category, duration) DO NOTHING
                """, (
                    "vpn",
                    "کانفیگ VPN",
                    duration,
                    0,
                    0
                ))

        conn.commit()


# =========================================================
# HELPERS
# =========================================================

def is_admin(user_id):
    return ADMIN_ID and str(user_id) == str(ADMIN_ID)


def format_price(price):
    if price == 0:
        return "قیمت تعیین نشده"
    return f"{price:,} تومان"


def save_user(user):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (id, username, first_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name
            """, (
                user.id,
                user.username,
                user.first_name
            ))
        conn.commit()


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 فروشگاه", callback_data="shop")],
        [InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders")],
        [InlineKeyboardButton("👤 حساب من", callback_data="account")],
        [InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
    ])


def shop_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📱 تلگرام پریمیوم",
            callback_data="category:telegram"
        )],
        [InlineKeyboardButton(
            "🌐 VPN",
            callback_data="category:vpn"
        )],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back")],
    ])


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    await update.message.reply_text(
        "سلام 👋\n\n"
        "به فروشگاه ما خوش آمدید.\n\n"
        "محصول موردنظر خود را انتخاب کنید:",
        reply_markup=main_menu()
    )


# =========================================================
# SHOP
# =========================================================

async def show_category(query, category):

    title = "📱 تلگرام پریمیوم" if category == "telegram" else "🌐 VPN"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, duration, price, stock
                FROM products
                WHERE category = %s
                AND active = TRUE
                ORDER BY duration
            """, (category,))

            products = cur.fetchall()

    keyboard = []

    for product_id, duration, price, stock in products:

        if stock > 0 and price > 0:
            text = (
                f"{duration} ماهه | "
                f"{format_price(price)}"
            )
        elif price == 0:
            text = f"{duration} ماهه | قیمت تعیین نشده"
        else:
            text = f"{duration} ماهه | ناموجود"

        keyboard.append([
            InlineKeyboardButton(
                text,
                callback_data=f"product:{product_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="shop"
        )
    ])

    await query.edit_message_text(
        f"{title}\n\n"
        "پلن موردنظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_product(query, product_id):

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, category, name, duration, price, stock
                FROM products
                WHERE id = %s
            """, (product_id,))

            product = cur.fetchone()

    if not product:
        await query.answer("محصول پیدا نشد.", show_alert=True)
        return

    product_id, category, name, duration, price, stock = product

    if price == 0:
        text = (
            f"{name}\n"
            f"پلن: {duration} ماهه\n\n"
            "❌ قیمت این پلن هنوز تعیین نشده است."
        )

        keyboard = [[
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data=f"category:{category}"
            )
        ]]

    elif stock <= 0:
        text = (
            f"{name}\n"
            f"پلن: {duration} ماهه\n\n"
            f"💰 قیمت: {format_price(price)}\n"
            "❌ این پلن فعلاً ناموجود است."
        )

        keyboard = [[
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data=f"category:{category}"
            )
        ]]

    else:
        text = (
            f"{name}\n"
            f"پلن: {duration} ماهه\n\n"
            f"💰 قیمت: {format_price(price)}\n"
            f"📦 موجودی: {stock}\n\n"
            "برای ثبت سفارش روی دکمه زیر بزنید."
        )

        keyboard = [
            [InlineKeyboardButton(
                "🛒 ثبت سفارش",
                callback_data=f"buy:{product_id}"
            )],
            [InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data=f"category:{category}"
            )]
        ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# CREATE ORDER
# =========================================================

async def create_order(query, product_id):

    user = query.from_user

    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id, name, duration, price, stock
                FROM products
                WHERE id = %s
                FOR UPDATE
            """, (product_id,))

            product = cur.fetchone()

            if not product:
                await query.answer(
                    "محصول پیدا نشد.",
                    show_alert=True
                )
                return

            pid, name, duration, price, stock = product

            if price <= 0:
                await query.answer(
                    "قیمت این محصول هنوز تعیین نشده است.",
                    show_alert=True
                )
                return

            if stock <= 0:
                await query.answer(
                    "این محصول ناموجود است.",
                    show_alert=True
                )
                return

            cur.execute("""
                INSERT INTO orders
                (user_id, product_id, price, status)
                VALUES (%s, %s, %s, 'pending')
                RETURNING id
            """, (
                user.id,
                product_id,
                price
            ))

            order_id = cur.fetchone()[0]

            # رزرو یک موجودی
            cur.execute("""
                UPDATE products
                SET stock = stock - 1
                WHERE id = %s
            """, (product_id,))

        conn.commit()

    await query.edit_message_text(
        f"✅ سفارش شما ثبت شد.\n\n"
        f"🧾 شماره سفارش: #{order_id}\n"
        f"📦 محصول: {name}\n"
        f"📅 مدت: {duration} ماه\n"
        f"💰 مبلغ: {format_price(price)}\n\n"
        "وضعیت سفارش: ⏳ در انتظار پرداخت",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🔙 فروشگاه",
                callback_data="shop"
            )]
        ])
    )


# =========================================================
# USER ORDERS
# =========================================================

async def show_orders(query):

    user_id = query.from_user.id

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    orders.id,
                    products.name,
                    products.duration,
                    orders.price,
                    orders.status
                FROM orders
                JOIN products
                ON products.id = orders.product_id
                WHERE orders.user_id = %s
                ORDER BY orders.id DESC
                LIMIT 20
            """, (user_id,))

            orders = cur.fetchall()

    if not orders:
        text = "📦 شما هنوز سفارشی ثبت نکرده‌اید."

    else:
        lines = ["📦 سفارش‌های شما:\n"]

        status_names = {
            "pending": "⏳ در انتظار پرداخت",
            "approved": "✅ تأیید شده",
            "rejected": "❌ رد شده",
        }

        for order_id, name, duration, price, status in orders:
            lines.append(
                f"🧾 #{order_id}\n"
                f"{name} - {duration} ماه\n"
                f"💰 {format_price(price)}\n"
                f"وضعیت: {status_names.get(status, status)}\n"
            )

        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="back"
            )]
        ])
    )


# =========================================================
# ACCOUNT
# =========================================================

async def show_account(query):

    user = query.from_user

    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT COUNT(*)
                FROM orders
                WHERE user_id = %s
            """, (user.id,))

            order_count = cur.fetchone()[0]

    await query.edit_message_text(
        "👤 حساب شما\n\n"
        f"نام: {user.first_name}\n"
        f"شناسه: {user.id}\n"
        f"📦 تعداد سفارش‌ها: {order_count}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="back"
            )]
        ])
    )


# =========================================================
# CALLBACK HANDLER
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    user = query.from_user
    save_user(user)

    data = query.data

    if data == "shop":
        await query.edit_message_text(
            "🛒 فروشگاه\n\n"
            "محصول موردنظر را انتخاب کنید:",
            reply_markup=shop_menu()
        )

    elif data.startswith("category:"):
        category = data.split(":")[1]
        await show_category(query, category)

    elif data.startswith("product:"):
        product_id = int(data.split(":")[1])
        await show_product(query, product_id)

    elif data.startswith("buy:"):
        product_id = int(data.split(":")[1])
        await create_order(query, product_id)

    elif data == "orders":
        await show_orders(query)

    elif data == "account":
        await show_account(query)

    elif data == "support":
        await query.edit_message_text(
            "📞 پشتیبانی\n\n"
            "برای ارتباط با پشتیبانی پیام خود را ارسال کنید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔙 بازگشت",
                    callback_data="back"
                )]
            ])
        )

    elif data == "back":
        await query.edit_message_text(
            "👋 به فروشگاه ما خوش آمدید.\n\n"
            "لطفاً یک گزینه را انتخاب کنید:",
            reply_markup=main_menu()
        )

    # ---------------- ADMIN ----------------

    elif data == "admin":
        if not is_admin(user.id):
            await query.answer(
                "دسترسی غیرمجاز",
                show_alert=True
            )
            return

        await show_admin_menu(query)

    elif data == "admin_products":
        if is_admin(user.id):
            await show_admin_products(query)

    elif data.startswith("admin_price:"):
        if is_admin(user.id):
            product_id = int(data.split(":")[1])
            context.user_data["edit_product_id"] = product_id
            context.user_data["edit_type"] = "price"

            await query.edit_message_text(
                "💰 قیمت جدید را به تومان ارسال کنید.\n\n"
                "مثال:\n"
                "250000"
            )
            return "WAIT_ADMIN_VALUE"

    elif data.startswith("admin_stock:"):
        if is_admin(user.id):
            product_id = int(data.split(":")[1])
            context.user_data["edit_product_id"] = product_id
            context.user_data["edit_type"] = "stock"

            await query.edit_message_text(
                "📦 تعداد موجودی جدید را ارسال کنید.\n\n"
                "مثال:\n"
                "10"
            )
            return "WAIT_ADMIN_VALUE"

    elif data == "admin_orders":
        if is_admin(user.id):
            await show_admin_orders(query)

    elif data.startswith("approve:"):
        if is_admin(user.id):
            order_id = int(data.split(":")[1])
            await approve_order(query, order_id)

    elif data.startswith("reject:"):
        if is_admin(user.id):
            order_id = int(data.split(":")[1])
            await reject_order(query, order_id)

    elif data == "admin_stats":
        if is_admin(user.id):
            await show_admin_stats(query)


# =========================================================
# ADMIN MENU
# =========================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text(
            "❌ شما دسترسی مدیریت ندارید."
        )
        return

    keyboard = [
        [InlineKeyboardButton(
            "📦 مدیریت محصولات",
            callback_data="admin_products"
        )],
        [InlineKeyboardButton(
            "🧾 سفارش‌ها",
            callback_data="admin_orders"
        )],
        [InlineKeyboardButton(
            "📊 آمار",
            callback_data="admin_stats"
        )],
    ]

    await update.message.reply_text(
        "🔐 پنل مدیریت\n\n"
        "یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_admin_menu(query):

    await query.edit_message_text(
        "🔐 پنل مدیریت",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📦 مدیریت محصولات",
                callback_data="admin_products"
            )],
            [InlineKeyboardButton(
                "🧾 سفارش‌ها",
                callback_data="admin_orders"
            )],
            [InlineKeyboardButton(
                "📊 آمار",
                callback_data="admin_stats"
            )]
        ])
    )


async def show_admin_products(query):

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, category, name, duration, price, stock
                FROM products
                ORDER BY category, duration
            """)

            products = cur.fetchall()

    keyboard = []

    for product_id, category, name, duration, price, stock in products:

        category_name = (
            "📱 تلگرام"
            if category == "telegram"
            else "🌐 VPN"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"{category_name} {duration} ماهه",
                callback_data=f"admin_price:{product_id}"
            )
        ])

        keyboard.append([
            InlineKeyboardButton(
                f"💰 {format_price(price)} | 📦 {stock}",
                callback_data=f"admin_stock:{product_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin"
        )
    ])

    await query.edit_message_text(
        "📦 مدیریت محصولات\n\n"
        "برای تغییر قیمت روی ردیف محصول و برای تغییر موجودی روی ردیف قیمت/موجودی بزن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# ADMIN VALUE HANDLER
# =========================================================

async def admin_value_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not is_admin(user.id):
        return ConversationHandler.END

    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text(
            "❌ فقط عدد وارد کن."
        )
        return "WAIT_ADMIN_VALUE"

    value = int(text)

    product_id = context.user_data.get("edit_product_id")
    edit_type = context.user_data.get("edit_type")

    if not product_id:
        return ConversationHandler.END

    with get_db() as conn:
        with conn.cursor() as cur:

            if edit_type == "price":
                cur.execute("""
                    UPDATE products
                    SET price = %s
                    WHERE id = %s
                """, (value, product_id))

                message = (
                    f"✅ قیمت با موفقیت تغییر کرد.\n"
                    f"قیمت جدید: {format_price(value)}"
                )

            else:
                cur.execute("""
                    UPDATE products
                    SET stock = %s
                    WHERE id = %s
                """, (value, product_id))

                message = (
                    f"✅ موجودی با موفقیت تغییر کرد.\n"
                    f"موجودی جدید: {value}"
                )

        conn.commit()

    context.user_data.clear()

    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📦 مدیریت محصولات",
                callback_data="admin_products"
            )]
        ])
    )

    return ConversationHandler.END


# =========================================================
# ADMIN ORDERS
# =========================================================

async def show_admin_orders(query):

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    orders.id,
                    orders.user_id,
                    products.name,
                    products.duration,
                    orders.price,
                    orders.status
                FROM orders
                JOIN products
                ON products.id = orders.product_id
                ORDER BY orders.id DESC
                LIMIT 20
            """)

            orders = cur.fetchall()

    if not orders:
        await query.edit_message_text(
            "🧾 هنوز سفارشی ثبت نشده است.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔙 پنل مدیریت",
                    callback_data="admin"
                )]
            ])
        )
        return

    keyboard = []

    for order_id, user_id, name, duration, price, status in orders:

        status_icon = {
            "pending": "⏳",
            "approved": "✅",
            "rejected": "❌"
        }.get(status, "❓")

        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} سفارش #{order_id}",
                callback_data=f"admin_order:{order_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin"
        )
    ])

    await query.edit_message_text(
        "🧾 سفارش‌های اخیر:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def approve_order(query, order_id):

    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                UPDATE orders
                SET status = 'approved'
                WHERE id = %s
                AND status = 'pending'
                RETURNING user_id
            """, (order_id,))

            result = cur.fetchone()

        conn.commit()

    if not result:
        await query.answer(
            "این سفارش قابل تأیید نیست.",
            show_alert=True
        )
        return

    await query.answer(
        "سفارش تأیید شد.",
        show_alert=True
    )


async def reject_order(query, order_id):

    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT product_id, user_id
                FROM orders
                WHERE id = %s
                AND status = 'pending'
            """, (order_id,))

            order = cur.fetchone()

            if not order:
                await query.answer(
                    "این سفارش قابل رد کردن نیست.",
                    show_alert=True
                )
                return

            product_id, user_id = order

            cur.execute("""
                UPDATE orders
                SET status = 'rejected'
                WHERE id = %s
            """, (order_id,))

            # آزاد کردن موجودی رزرو شده
            cur.execute("""
                UPDATE products
                SET stock = stock + 1
                WHERE id = %s
            """, (product_id,))

        conn.commit()

    await query.answer(
        "سفارش رد شد و موجودی آزاد شد.",
        show_alert=True
    )


# =========================================================
# ADMIN STATS
# =========================================================

async def show_admin_stats(query):

    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("SELECT COUNT(*) FROM users")
            users = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM orders")
            orders = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*)
                FROM orders
                WHERE status = 'approved'
            """)
            approved = cur.fetchone()[0]

            cur.execute("""
                SELECT COALESCE(SUM(price), 0)
                FROM orders
                WHERE status = 'approved'
            """)
            revenue = cur.fetchone()[0]

    await query.edit_message_text(
        "📊 آمار فروشگاه\n\n"
        f"👥 کاربران: {users}\n"
        f"🧾 کل سفارش‌ها: {orders}\n"
        f"✅ سفارش‌های تأییدشده: {approved}\n"
        f"💰 فروش تأییدشده: {format_price(revenue)}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🔙 پنل مدیریت",
                callback_data="admin"
            )]
        ])
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    if not RENDER_URL:
        raise ValueError("RENDER_EXTERNAL_URL is not set")

    if not ADMIN_ID:
        raise ValueError("ADMIN_ID is not set")

    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))

    conversation_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                button_handler,
                pattern=r"^admin_(price|stock):"
            )
        ],
        states={
            "WAIT_ADMIN_VALUE": [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    admin_value_handler
                )
            ]
        },
        fallbacks=[]
    )

    app.add_handler(conversation_handler)

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="telegram",
        webhook_url=f"{RENDER_URL}/telegram",
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
