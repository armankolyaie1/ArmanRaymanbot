import os
import logging

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

import database as db


TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
ADMIN_ID = os.getenv("ADMIN_ID")


WAIT_ADMIN_VALUE = 1
WAIT_VPN_CONFIG = 2
WAIT_SUPPORT = 3


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


def is_admin(user_id):
    return bool(ADMIN_ID) and str(user_id) == str(ADMIN_ID)


def format_price(price):
    price = int(price or 0)
    return "قیمت تعیین نشده" if price <= 0 else f"{price:,} تومان"


def status_name(status):
    return {
        "pending_payment": "⏳ در انتظار پرداخت",
        "approved": "✅ تأیید شده",
        "rejected": "❌ رد شده",
    }.get(status, status)


def main_menu():
    rows = [
        [InlineKeyboardButton("🛒 فروشگاه", callback_data="shop")],
        [InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders")],
        [InlineKeyboardButton("👤 حساب من", callback_data="account")],
        [InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
    ]

    if ADMIN_ID:
        rows.append([
            InlineKeyboardButton("🔐 پنل مدیریت", callback_data="admin")
        ])

    return InlineKeyboardMarkup(rows)


def shop_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📱 تلگرام پریمیوم",
                callback_data="category:telegram"
            )
        ],
        [
            InlineKeyboardButton(
                "🌐 VPN / VLESS",
                callback_data="category:vpn"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="back"
            )
        ],
    ])


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📦 مدیریت محصولات",
                callback_data="admin_products"
            )
        ],
        [
            InlineKeyboardButton(
                "🧾 سفارش‌ها",
                callback_data="admin_orders"
            )
        ],
        [
            InlineKeyboardButton(
                "🔐 موجودی VLESS",
                callback_data="admin_inventory"
            )
        ],
        [
            InlineKeyboardButton(
                "📞 پیام‌های پشتیبانی",
                callback_data="admin_support"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 آمار",
                callback_data="admin_stats"
            )
        ],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await db.save_user(user)

    await update.message.reply_text(
        "سلام 👋\n\n"
        "به فروشگاه ما خوش آمدید.\n\n"
        "محصول موردنظر را انتخاب کنید:",
        reply_markup=main_menu(),
    )


async def show_category(query, category):
    title = (
        "📱 تلگرام پریمیوم"
        if category == "telegram"
        else "🌐 VPN / VLESS"
    )

    products = await db.get_products(category)

    keyboard = []

    for product_id, _, _, duration, price, stock, active in products:
        if not active:
            continue

        if price <= 0:
            label = f"{duration} ماهه | قیمت تعیین نشده"
        elif stock <= 0:
            label = f"{duration} ماهه | ناموجود"
        else:
            label = f"{duration} ماهه | {format_price(price)}"

        keyboard.append([
            InlineKeyboardButton(
                label,
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
        f"{title}\n\nپلن موردنظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_product(query, product_id):
    product = await db.get_product(product_id)

    if not product:
        await query.answer(
            "محصول پیدا نشد.",
            show_alert=True
        )
        return

    pid, category, name, duration, price, stock, active = product

    if not active:
        text = (
            f"{name}\n\n"
            "❌ این محصول غیرفعال است."
        )

        keyboard = [[
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data=f"category:{category}"
            )
        ]]

    elif price <= 0:
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
            f"پلن: {duration} ماهه\n"
            f"💰 قیمت: {format_price(price)}\n\n"
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
            f"پلن: {duration} ماهه\n"
            f"💰 قیمت: {format_price(price)}\n"
            f"📦 موجودی: {stock}\n\n"
            "برای ادامه روی ثبت سفارش بزنید."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🛒 ثبت سفارش",
                    callback_data=f"buy:{pid}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 بازگشت",
                    callback_data=f"category:{category}"
                )
            ],
        ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def create_order(query, product_id):
    try:
        order_id, name, duration, price = await db.create_order(
            query.from_user.id,
            product_id,
        )

    except ValueError as exc:
        messages = {
            "PRODUCT_NOT_FOUND": "محصول پیدا نشد.",
            "PRODUCT_INACTIVE": "این محصول غیرفعال است.",
            "PRICE_NOT_SET": "قیمت این محصول هنوز تعیین نشده است.",
            "OUT_OF_STOCK": "این محصول فعلاً ناموجود است.",
        }

        await query.answer(
            messages.get(
                str(exc),
                "ثبت سفارش انجام نشد."
            ),
            show_alert=True,
        )
        return

    await query.edit_message_text(
        f"✅ سفارش #{order_id} ایجاد شد.\n\n"
        f"📦 محصول: {name}\n"
        f"📅 مدت: {duration} ماه\n"
        f"💰 مبلغ: {format_price(price)}\n\n"
        "⏳ وضعیت: در انتظار پرداخت\n\n"
        "💳 درگاه پرداخت در این نسخه جدا از منطق سفارش قرار گرفته است. "
        "تا زمان اتصال درگاه، پرداخت توسط مدیریت تأیید می‌شود.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📦 سفارش‌های من",
                    callback_data="orders"
                )
            ],
            [
                InlineKeyboardButton(
                    "🛒 فروشگاه",
                    callback_data="shop"
                )
            ],
        ]),
    )


async def show_orders(query):
    orders = await db.get_user_orders(
        query.from_user.id
    )

    if not orders:
        text = "📦 شما هنوز سفارشی ثبت نکرده‌اید."

    else:
        lines = ["📦 سفارش‌های شما:\n"]

        for oid, name, duration, price, status, created_at in orders:
            lines.append(
                f"🧾 #{oid}\n"
                f"{name} - {duration} ماه\n"
                f"💰 {format_price(price)}\n"
                f"وضعیت: {status_name(status)}\n"
            )

        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 بازگشت",
                    callback_data="back"
                )
            ]
        ]),
    )


async def show_account(query):
    orders = await db.get_user_orders(
        query.from_user.id,
        limit=1000,
    )

    await query.edit_message_text(
        "👤 حساب شما\n\n"
        f"نام: {query.from_user.first_name or '-'}\n"
        f"شناسه: {query.from_user.id}\n"
        f"📦 تعداد سفارش‌ها: {len(orders)}",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 بازگشت",
                    callback_data="back"
                )
            ]
        ]),
    )


async def show_support(query):
    await query.edit_message_text(
        "📞 پشتیبانی\n\n"
        "پیام خود را در یک پیام ارسال کنید تا برای مدیریت فرستاده شود.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 لغو",
                    callback_data="back"
                )
            ]
        ]),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    data = query.data

    try:
        if data == "shop":
            await query.edit_message_text(
                "🛒 فروشگاه\n\n"
                "محصول موردنظر را انتخاب کنید:",
                reply_markup=shop_menu(),
            )

        elif data.startswith("category:"):
            await show_category(
                query,
                data.split(":", 1)[1],
            )

        elif data.startswith("product:"):
            await show_product(
                query,
                int(data.split(":", 1)[1]),
            )

        elif data.startswith("buy:"):
            await create_order(
                query,
                int(data.split(":", 1)[1]),
            )

        elif data == "orders":
            await show_orders(query)

        elif data == "account":
            await show_account(query)

        elif data == "support":
            context.user_data["support_mode"] = True
            await show_support(query)

        elif data == "back":
            context.user_data.clear()

            await query.edit_message_text(
                "👋 خوش آمدید.\n\n"
                "لطفاً یک گزینه را انتخاب کنید:",
                reply_markup=main_menu(),
            )

        elif data == "admin":
            if is_admin(query.from_user.id):
                await show_admin_menu(query)

        elif data == "admin_products":
            if is_admin(query.from_user.id):
                await show_admin_products(query)

        elif data.startswith("admin_price:"):
            if is_admin(query.from_user.id):
                context.user_data["edit_product_id"] = int(
                    data.split(":")[1]
                )
                context.user_data["edit_type"] = "price"

                await query.edit_message_text(
                    "💰 قیمت جدید را به تومان ارسال کنید:"
                )

                return WAIT_ADMIN_VALUE

        elif data.startswith("admin_stock:"):
            if is_admin(query.from_user.id):
                context.user_data["edit_product_id"] = int(
                    data.split(":")[1]
                )
                context.user_data["edit_type"] = "stock"

                await query.edit_message_text(
                    "📦 موجودی جدید را ارسال کنید:"
                )

                return WAIT_ADMIN_VALUE

        elif data.startswith("admin_add_vpn:"):
            if is_admin(query.from_user.id):
                product_id = int(data.split(":")[1])

                context.user_data["vpn_product_id"] = product_id

                await query.edit_message_text(
                    "🔐 کانفیگ VLESS را ارسال کن.\n\n"
                    "هر پیام فقط یک کانفیگ باشد."
                )

                return WAIT_VPN_CONFIG

        elif data == "admin_orders":
            if is_admin(query.from_user.id):
                await show_admin_orders(query)

        elif data.startswith("admin_order:"):
            if is_admin(query.from_user.id):
                await show_admin_order(
                    query,
                    int(data.split(":")[1]),
                )

        elif data.startswith("approve:"):
            if is_admin(query.from_user.id):
                await admin_approve(
                    query,
                    int(data.split(":")[1]),
                )

        elif data.startswith("reject:"):
            if is_admin(query.from_user.id):
                await admin_reject(
                    query,
                    int(data.split(":")[1]),
                )

        elif data == "admin_inventory":
            if is_admin(query.from_user.id):
                await show_inventory(query)

        elif data == "admin_stats":
            if is_admin(query.from_user.id):
                await show_admin_stats(query)

        elif data == "admin_support":
            if is_admin(query.from_user.id):
                await show_admin_support(query)

        elif data.startswith("admin_support_reply:"):
            if is_admin(query.from_user.id):
                context.user_data["reply_support_id"] = int(
                    data.split(":")[1]
                )

                await query.edit_message_text(
                    "✉️ پاسخ را ارسال کن:"
                )

                return WAIT_SUPPORT

    except Exception:
        logger.exception("Callback failed")

        try:
            await query.answer(
                "خطای داخلی رخ داد.",
                show_alert=True,
            )
        except Exception:
            pass


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "❌ دسترسی غیرمجاز."
        )
        return

    await update.message.reply_text(
        "🔐 پنل مدیریت",
        reply_markup=admin_keyboard(),
    )


async def show_admin_menu(query):
    await query.edit_message_text(
        "🔐 پنل مدیریت",
        reply_markup=admin_keyboard(),
    )


async def show_admin_products(query):
    products = await db.get_products()

    keyboard = []

    for pid, category, name, duration, price, stock, active in products:
        cat = "📱" if category == "telegram" else "🌐"

        keyboard.append([
            InlineKeyboardButton(
                f"{cat} {duration} ماهه | {format_price(price)}",
                callback_data=f"admin_price:{pid}",
            )
        ])

        if category == "telegram":
            keyboard.append([
                InlineKeyboardButton(
                    f"📦 موجودی تلگرام: {stock}",
                    callback_data=f"admin_stock:{pid}",
                )
            ])

        else:
            keyboard.append([
                InlineKeyboardButton(
                    f"➕ افزودن VLESS {duration} ماهه",
                    callback_data=f"admin_add_vpn:{pid}",
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin"
        )
    ])

    await query.edit_message_text(
        "📦 مدیریت محصولات:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_admin_orders(query):
    orders = await db.get_admin_orders()

    if not orders:
        await query.edit_message_text(
            "🧾 هنوز سفارشی ثبت نشده.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 پنل مدیریت",
                        callback_data="admin"
                    )
                ]
            ]),
        )
        return

    keyboard = []

    for oid, user_id, name, duration, price, status, created_at in orders:
        keyboard.append([
            InlineKeyboardButton(
                f"{status_name(status)} #{oid} | {format_price(price)}",
                callback_data=f"admin_order:{oid}",
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
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_admin_order(query, order_id):
    order = await db.get_order(order_id)

    if not order:
        await query.answer(
            "سفارش پیدا نشد.",
            show_alert=True,
        )
        return

    (
        oid,
        user_id,
        product_id,
        category,
        name,
        duration,
        price,
        status,
        created,
    ) = order

    text = (
        f"🧾 سفارش #{oid}\n\n"
        f"👤 کاربر: {user_id}\n"
        f"📦 {name}\n"
        f"📅 {duration} ماه\n"
        f"💰 {format_price(price)}\n"
        f"📌 وضعیت: {status_name(status)}"
    )

    keyboard = []

    if status == "pending_payment":
        keyboard.append([
            InlineKeyboardButton(
                "✅ تأیید پرداخت/تحویل",
                callback_data=f"approve:{oid}",
            ),
            InlineKeyboardButton(
                "❌ رد",
                callback_data=f"reject:{oid}",
            ),
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 سفارش‌ها",
            callback_data="admin_orders"
        )
    ])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_approve(query, order_id):
    delivery, result = await db.approve_order(order_id)

    if result != "OK":
        messages = {
            "NOT_FOUND": "سفارش پیدا نشد.",
            "NOT_PENDING": "این سفارش قبلاً پردازش شده.",
            "OUT_OF_STOCK": "کانفیگ VLESS موجود نیست.",
        }

        await query.answer(
            messages.get(
                result,
                "تأیید انجام نشد."
            ),
            show_alert=True,
        )
        return

    order = await db.get_order(order_id)

    if order:
        user_id = order[1]

        try:
            if delivery:
                text = (
                    f"✅ سفارش #{order_id} تأیید شد.\n\n"
                    "🔐 کانفیگ VLESS:\n\n"
                    f"{delivery}"
                )

            else:
                text = (
                    f"✅ سفارش #{order_id} تأیید شد.\n\n"
                    "📱 محصول شما تأیید شد و تحویل آن "
                    "طبق روش فروش شما انجام می‌شود."
                )

            await query.get_bot().send_message(
                chat_id=user_id,
                text=text,
            )

        except Exception:
            logger.exception(
                "Delivery notification failed"
            )

    await query.answer(
        "سفارش تأیید شد.",
        show_alert=True,
    )

    await show_admin_order(
        query,
        order_id,
    )


async def admin_reject(query, order_id):
    result = await db.reject_order(order_id)

    if not result:
        await query.answer(
            "این سفارش قابل رد نیست.",
            show_alert=True,
        )
        return

    _, user_id = result

    try:
        await query.get_bot().send_message(
            chat_id=user_id,
            text=f"❌ سفارش #{order_id} رد شد.",
        )

    except Exception:
        logger.exception(
            "Reject notification failed"
        )

    await query.answer(
        "سفارش رد شد.",
        show_alert=True,
    )

    await show_admin_order(
        query,
        order_id,
    )


async def show_inventory(query):
    inventory = await db.get_vpn_inventory()

    if not inventory:
        text = "🔐 هیچ کانفیگی ثبت نشده است."

    else:
        lines = ["🔐 موجودی VLESS:\n"]

        for cid, name, duration, status, created in inventory:
            lines.append(
                f"#{cid} | {duration} ماه | {status}"
            )

        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📦 مدیریت محصولات",
                    callback_data="admin_products"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 پنل مدیریت",
                    callback_data="admin"
                )
            ],
        ]),
    )


async def admin_value_handler(update, context):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip().replace(",", "")

    if not text.isdigit():
        await update.message.reply_text(
            "❌ فقط عدد وارد کن."
        )
        return WAIT_ADMIN_VALUE

    product_id = context.user_data.get(
        "edit_product_id"
    )

    edit_type = context.user_data.get(
        "edit_type"
    )

    if not product_id:
        return ConversationHandler.END

    value = int(text)

    if edit_type == "price":
        await db.update_product_value(
            product_id,
            "price",
            value,
        )

        message = (
            f"✅ قیمت جدید: {format_price(value)}"
        )

    else:
        await db.update_product_value(
            product_id,
            "stock",
            value,
        )

        message = (
            f"✅ موجودی جدید: {value}"
        )

    context.user_data.clear()

    await update.message.reply_text(
        message,
        reply_markup=admin_keyboard(),
    )

    return ConversationHandler.END


async def vpn_config_handler(update, context):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    config = update.message.text.strip()

    product_id = context.user_data.get(
        "vpn_product_id"
    )

    if not product_id:
        await update.message.reply_text(
            "❌ محصول VLESS مشخص نیست."
        )
        return ConversationHandler.END

    try:
        cid = await db.add_vpn_config(
            product_id,
            config,
        )

    except ValueError:
        await update.message.reply_text(
            "❌ کانفیگ خالی است."
        )
        return WAIT_VPN_CONFIG

    except Exception:
        logger.exception(
            "Could not add VLESS config"
        )

        await update.message.reply_text(
            "❌ ثبت کانفیگ انجام نشد؛ احتمالاً تکراری است."
        )

        return WAIT_VPN_CONFIG

    context.user_data.clear()

    await update.message.reply_text(
        f"✅ کانفیگ VLESS با شناسه #{cid} ثبت شد.",
        reply_markup=admin_keyboard(),
    )

    return ConversationHandler.END


async def support_handler(update, context):
    user = update.effective_user

    if (
        context.user_data.get("reply_support_id")
        and is_admin(user.id)
    ):
        support_id = context.user_data[
            "reply_support_id"
        ]

        reply = update.message.text.strip()

        if reply:
            result = await db.reply_support_message(
                support_id,
                reply,
            )

            if result:
                user_id = result

                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"📞 پاسخ پشتیبانی:\n\n{reply}",
                    )

                except Exception:
                    logger.exception(
                        "Support reply delivery failed"
                    )

            context.user_data.clear()

            await update.message.reply_text(
                "✅ پاسخ ارسال شد.",
                reply_markup=admin_keyboard(),
            )

        return

    if not context.user_data.get(
        "support_mode"
    ):
        return

    message = update.message.text.strip()

    if not message:
        return

    await db.create_support_message(
        user.id,
        message,
    )

    context.user_data.clear()

    await update.message.reply_text(
        "✅ پیام شما برای پشتیبانی ارسال شد.",
        reply_markup=main_menu(),
    )

    if ADMIN_ID:
        try:
            support_id = await db.latest_support_id(
                user.id
            )

            await context.bot.send_message(
                chat_id=int(ADMIN_ID),
                text=(
                    "📞 پیام پشتیبانی جدید\n\n"
                    f"👤 {user.id}\n\n"
                    f"{message}"
                ),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "✉️ پاسخ",
                            callback_data=(
                                f"admin_support_reply:{support_id}"
                            ),
                        )
                    ]
                ]),
            )

        except Exception:
            logger.exception(
                "Support notification failed"
            )


async def show_admin_support(query):
    messages = await db.get_support_messages()

    if not messages:
        text = (
            "📞 پیام پشتیبانی باز وجود ندارد."
        )

        keyboard = [[
            InlineKeyboardButton(
                "🔙 پنل مدیریت",
                callback_data="admin"
            )
        ]]

    else:
        lines = ["📞 پیام‌های پشتیبانی:\n"]
        keyboard = []

        for sid, user_id, message, status, created_at in messages:
            lines.append(
                f"#{sid} | 👤 {user_id}\n"
                f"{message}\n"
            )

            keyboard.append([
                InlineKeyboardButton(
                    f"✉️ پاسخ #{sid}",
                    callback_data=(
                        f"admin_support_reply:{sid}"
                    ),
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🔙 پنل مدیریت",
                callback_data="admin"
            )
        ])

        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_support_reply_handler(update, context):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    support_id = context.user_data.get(
        "reply_support_id"
    )

    if not support_id:
        return ConversationHandler.END

    reply = update.message.text.strip()

    if not reply:
        return WAIT_SUPPORT

    user_id = await db.reply_support_message(
        support_id,
        reply,
    )

    if user_id:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📞 پاسخ پشتیبانی:\n\n{reply}",
            )

        except Exception:
            logger.exception(
                "Support delivery failed"
            )

    context.user_data.clear()

    await update.message.reply_text(
        "✅ پاسخ ارسال شد.",
        reply_markup=admin_keyboard(),
    )

    return ConversationHandler.END


async def show_admin_stats(query):
    (
        users,
        orders,
        approved,
        revenue,
        vpn_available,
    ) = await db.stats()

    await query.edit_message_text(
        "📊 آمار فروشگاه\n\n"
        f"👥 کاربران: {users}\n"
        f"🧾 سفارش‌ها: {orders}\n"
        f"✅ تأییدشده: {approved}\n"
        f"💰 فروش تأییدشده: {format_price(revenue)}\n"
        f"🔐 VLESS آزاد: {vpn_available}",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 پنل مدیریت",
                    callback_data="admin"
                )
            ]
        ]),
    )


async def post_init(application):
    await db.init_db()


async def post_shutdown(application):
    await db.close_pool()


async def error_handler(update, context):
    logger.error(
        "Unhandled error: %r",
        context.error,
        exc_info=context.error,
    )


def main():
    if not TOKEN:
        raise ValueError(
            "BOT_TOKEN is not set"
        )

    if not RENDER_URL:
        raise ValueError(
            "RENDER_EXTERNAL_URL is not set"
        )

    if not ADMIN_ID:
        raise ValueError(
            "ADMIN_ID is not set"
        )

    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command,
        )
    )

    admin_value_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                button_handler,
                pattern=r"^admin_(price|stock):",
            )
        ],
        states={
            WAIT_ADMIN_VALUE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    admin_value_handler,
                )
            ]
        },
        fallbacks=[],
        allow_reentry=True,
    )

    application.add_handler(
        admin_value_conversation
    )

    vpn_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                button_handler,
                pattern=r"^admin_add_vpn:",
            )
        ],
        states={
            WAIT_VPN_CONFIG: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    vpn_config_handler,
                )
            ]
        },
        fallbacks=[],
        allow_reentry=True,
    )

    application.add_handler(
        vpn_conversation
    )

    support_reply_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                button_handler,
                pattern=r"^admin_support_reply:",
            )
        ],
        states={
            WAIT_SUPPORT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    admin_support_reply_handler,
                )
            ]
        },
        fallbacks=[],
        allow_reentry=True,
    )

    application.add_handler(
        support_reply_conversation
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            support_handler,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    application.add_error_handler(
        error_handler
    )

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="telegram",
        webhook_url=(
            f"{RENDER_URL.rstrip('/')}/telegram"
        ),
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
