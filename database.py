import os
import logging

from psycopg_pool import AsyncConnectionPool


logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

pool = None


# ---------------------------------------------------------
# DATABASE POOL
# ---------------------------------------------------------

async def _get_pool():
    global pool

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set")

    if pool is None:
        pool = AsyncConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=10,
            open=False,
            kwargs={
                "autocommit": False,
            },
        )

        await pool.open()
        await pool.wait()

    return pool


async def close_pool():
    global pool

    if pool is not None:
        await pool.close()
        pool = None


# ---------------------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------------------

async def init_db():
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            # USERS
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # PRODUCTS
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    price BIGINT NOT NULL DEFAULT 0,
                    stock INTEGER NOT NULL DEFAULT 0,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(category, duration)
                )
            """)

            # VLESS CONFIGS
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS vpn_configs (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER NOT NULL
                        REFERENCES products(id)
                        ON DELETE CASCADE,
                    config TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'available',
                    assigned_order_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    assigned_at TIMESTAMP
                )
            """)

            # ORDERS
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL
                        REFERENCES users(id),
                    product_id INTEGER NOT NULL
                        REFERENCES products(id),
                    price BIGINT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_payment',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # PAYMENTS
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL
                        REFERENCES orders(id)
                        ON DELETE CASCADE,
                    amount BIGINT NOT NULL,
                    gateway TEXT,
                    authority TEXT,
                    ref_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    verified_at TIMESTAMP
                )
            """)

            # SUPPORT
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS support_messages (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL
                        REFERENCES users(id),
                    message TEXT NOT NULL,
                    reply TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    replied_at TIMESTAMP
                )
            """)

            # -------------------------------------------------
            # SAFE MIGRATIONS
            # -------------------------------------------------

            await cur.execute("""
                ALTER TABLE products
                ADD COLUMN IF NOT EXISTS updated_at
                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """)

            await cur.execute("""
                ALTER TABLE orders
                ADD COLUMN IF NOT EXISTS updated_at
                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """)

            await cur.execute("""
                ALTER TABLE vpn_configs
                ADD COLUMN IF NOT EXISTS assigned_order_id INTEGER
            """)

            await cur.execute("""
                ALTER TABLE vpn_configs
                ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP
            """)

            # -------------------------------------------------
            # DEFAULT PRODUCTS
            # -------------------------------------------------

            for duration in (1, 3, 6, 12):

                await cur.execute("""
                    INSERT INTO products
                    (category, name, duration, price, stock)
                    VALUES (
                        'telegram',
                        'تلگرام پریمیوم',
                        %s,
                        0,
                        0
                    )
                    ON CONFLICT (category, duration)
                    DO NOTHING
                """, (duration,))

                await cur.execute("""
                    INSERT INTO products
                    (category, name, duration, price, stock)
                    VALUES (
                        'vpn',
                        'کانفیگ VLESS',
                        %s,
                        0,
                        0
                    )
                    ON CONFLICT (category, duration)
                    DO NOTHING
                """, (duration,))

            # -------------------------------------------------
            # SYNCHRONIZE VPN STOCK
            # -------------------------------------------------

            await cur.execute("""
                UPDATE products p
                SET
                    stock = (
                        SELECT COUNT(*)
                        FROM vpn_configs v
                        WHERE v.product_id = p.id
                          AND v.status = 'available'
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE p.category = 'vpn'
            """)

            # -------------------------------------------------
            # INDEXES
            # -------------------------------------------------

            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_user_id
                ON orders(user_id, id DESC)
            """)

            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status
                ON orders(status, id DESC)
            """)

            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_product
                ON orders(product_id, id DESC)
            """)

            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_vpn_product_status
                ON vpn_configs(product_id, status, id)
            """)

            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_vpn_status
                ON vpn_configs(status, id)
            """)

            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_support_status
                ON support_messages(status, id DESC)
            """)

            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_support_user
                ON support_messages(user_id, id DESC)
            """)

            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_payments_order
                ON payments(order_id, id DESC)
            """)

        await conn.commit()


# ---------------------------------------------------------
# USERS
# ---------------------------------------------------------

async def save_user(user):
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                INSERT INTO users (
                    id,
                    username,
                    first_name
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name
                WHERE
                    users.username IS DISTINCT FROM EXCLUDED.username
                    OR
                    users.first_name IS DISTINCT FROM EXCLUDED.first_name
            """, (
                user.id,
                user.username,
                user.first_name,
            ))

        await conn.commit()


# ---------------------------------------------------------
# PRODUCTS
# ---------------------------------------------------------

async def get_products(category=None):
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            if category:
                await cur.execute("""
                    SELECT
                        id,
                        category,
                        name,
                        duration,
                        price,
                        stock,
                        active
                    FROM products
                    WHERE category = %s
                    ORDER BY duration
                """, (category,))

            else:
                await cur.execute("""
                    SELECT
                        id,
                        category,
                        name,
                        duration,
                        price,
                        stock,
                        active
                    FROM products
                    ORDER BY category, duration
                """)

            return await cur.fetchall()


async def get_product(product_id):
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                SELECT
                    id,
                    category,
                    name,
                    duration,
                    price,
                    stock,
                    active
                FROM products
                WHERE id = %s
            """, (product_id,))

            return await cur.fetchone()


# ---------------------------------------------------------
# CREATE ORDER
# ---------------------------------------------------------

async def create_order(user_id, product_id):
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                SELECT
                    id,
                    category,
                    name,
                    duration,
                    price,
                    stock,
                    active
                FROM products
                WHERE id = %s
                FOR UPDATE
            """, (product_id,))

            product = await cur.fetchone()

            if not product:
                raise ValueError("PRODUCT_NOT_FOUND")

            (
                pid,
                category,
                name,
                duration,
                price,
                stock,
                active,
            ) = product

            if not active:
                raise ValueError("PRODUCT_INACTIVE")

            if price <= 0:
                raise ValueError("PRICE_NOT_SET")

            # VLESS availability
            if category == "vpn":

                await cur.execute("""
                    SELECT 1
                    FROM vpn_configs
                    WHERE product_id = %s
                      AND status = 'available'
                    LIMIT 1
                """, (product_id,))

                available = await cur.fetchone()

                if not available:
                    raise ValueError("OUT_OF_STOCK")

            # Telegram stock
            elif stock <= 0:
                raise ValueError("OUT_OF_STOCK")

            await cur.execute("""
                INSERT INTO orders (
                    user_id,
                    product_id,
                    price,
                    status
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    'pending_payment'
                )
                RETURNING id
            """, (
                user_id,
                product_id,
                price,
            ))

            order_id = (await cur.fetchone())[0]

        await conn.commit()

    return order_id, name, duration, price


# ---------------------------------------------------------
# USER ORDERS
# ---------------------------------------------------------

async def get_user_orders(user_id, limit=20):
    p = await _get_pool()

    # Safety limit
    limit = max(1, min(int(limit), 100))

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                SELECT
                    o.id,
                    p.name,
                    p.duration,
                    o.price,
                    o.status,
                    o.created_at
                FROM orders o
                JOIN products p
                    ON p.id = o.product_id
                WHERE o.user_id = %s
                ORDER BY o.id DESC
                LIMIT %s
            """, (
                user_id,
                limit,
            ))

            return await cur.fetchall()


async def get_user_order_count(user_id):
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                SELECT COUNT(*)
                FROM orders
                WHERE user_id = %s
            """, (user_id,))

            return (await cur.fetchone())[0]


# ---------------------------------------------------------
# SINGLE ORDER
# ---------------------------------------------------------

async def get_order(order_id):
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                SELECT
                    o.id,
                    o.user_id,
                    o.product_id,
                    p.category,
                    p.name,
                    p.duration,
                    o.price,
                    o.status,
                    o.created_at
                FROM orders o
                JOIN products p
                    ON p.id = o.product_id
                WHERE o.id = %s
            """, (order_id,))

            return await cur.fetchone()


# ---------------------------------------------------------
# APPROVE ORDER
# ---------------------------------------------------------

async def approve_order(order_id):
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            # Lock order
            await cur.execute("""
                SELECT
                    o.id,
                    o.user_id,
                    o.product_id,
                    p.category,
                    o.status
                FROM orders o
                JOIN products p
                    ON p.id = o.product_id
                WHERE o.id = %s
                FOR UPDATE
            """, (order_id,))

            order = await cur.fetchone()

            if not order:
                return None, "NOT_FOUND"

            (
                oid,
                user_id,
                product_id,
                category,
                status,
            ) = order

            if status != "pending_payment":
                return None, "NOT_PENDING"

            delivery = None

            # -------------------------------------------------
            # VPN DELIVERY
            # -------------------------------------------------

            if category == "vpn":

                await cur.execute("""
                    SELECT
                        id,
                        config
                    FROM vpn_configs
                    WHERE product_id = %s
                      AND status = 'available'
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                """, (product_id,))

                config = await cur.fetchone()

                if not config:
                    return None, "OUT_OF_STOCK"

                config_id, delivery = config

                await cur.execute("""
                    UPDATE vpn_configs
                    SET
                        status = 'assigned',
                        assigned_order_id = %s,
                        assigned_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (
                    order_id,
                    config_id,
                ))

                # Synchronize stock
                await cur.execute("""
                    UPDATE products
                    SET
                        stock = (
                            SELECT COUNT(*)
                            FROM vpn_configs
                            WHERE product_id = products.id
                              AND status = 'available'
                        ),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (product_id,))

            # -------------------------------------------------
            # TELEGRAM DELIVERY
            # -------------------------------------------------

            elif category == "telegram":

                # IMPORTANT:
                # Telegram stock is actually reduced
                # only when the order is approved.

                await cur.execute("""
                    UPDATE products
                    SET
                        stock = stock - 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND stock > 0
                """, (product_id,))

                if cur.rowcount != 1:
                    return None, "OUT_OF_STOCK"

            # -------------------------------------------------
            # APPROVE ORDER
            # -------------------------------------------------

            await cur.execute("""
                UPDATE orders
                SET
                    status = 'approved',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND status = 'pending_payment'
            """, (order_id,))

        await conn.commit()

    return delivery, "OK"


# ---------------------------------------------------------
# REJECT ORDER
# ---------------------------------------------------------

async def reject_order(order_id):
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                UPDATE orders
                SET
                    status = 'rejected',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND status = 'pending_payment'
                RETURNING id, user_id
            """, (order_id,))

            result = await cur.fetchone()

        await conn.commit()

    return result


# ---------------------------------------------------------
# VPN CONFIG
# ---------------------------------------------------------

async def add_vpn_config(product_id, config):
    config = (config or "").strip()

    if not config:
        raise ValueError("EMPTY_CONFIG")

    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                INSERT INTO vpn_configs (
                    product_id,
                    config
                )
                VALUES (
                    %s,
                    %s
                )
                RETURNING id
            """, (
                product_id,
                config,
            ))

            config_id = (await cur.fetchone())[0]

            await cur.execute("""
                UPDATE products
                SET
                    stock = (
                        SELECT COUNT(*)
                        FROM vpn_configs
                        WHERE product_id = products.id
                          AND status = 'available'
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (product_id,))

        await conn.commit()

    return config_id


async def get_vpn_inventory(limit=100):
    p = await _get_pool()

    limit = max(1, min(int(limit), 200))

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                SELECT
                    v.id,
                    p.name,
                    p.duration,
                    v.status,
                    v.created_at
                FROM vpn_configs v
                JOIN products p
                    ON p.id = v.product_id
                ORDER BY v.id DESC
                LIMIT %s
            """, (limit,))

            return await cur.fetchall()


# ---------------------------------------------------------
# ADMIN ORDERS
# ---------------------------------------------------------

async def get_admin_orders(limit=30):
    p = await _get_pool()

    limit = max(1, min(int(limit), 100))

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                SELECT
                    o.id,
                    o.user_id,
                    p.name,
                    p.duration,
                    o.price,
                    o.status,
                    o.created_at
                FROM orders o
                JOIN products p
                    ON p.id = o.product_id
                ORDER BY o.id DESC
                LIMIT %s
            """, (limit,))

            return await cur.fetchall()


# ---------------------------------------------------------
# PRODUCT MANAGEMENT
# ---------------------------------------------------------

async def update_product_value(product_id, field, value):
    if field not in (
        "price",
        "stock",
        "active",
    ):
        raise ValueError("INVALID_FIELD")

    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            if field == "price":

                await cur.execute("""
                    UPDATE products
                    SET
                        price = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (
                    value,
                    product_id,
                ))

            elif field == "stock":

                # Stock can be manually changed only
                # for Telegram products.
                await cur.execute("""
                    UPDATE products
                    SET
                        stock = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND category <> 'vpn'
                """, (
                    value,
                    product_id,
                ))

            elif field == "active":

                await cur.execute("""
                    UPDATE products
                    SET
                        active = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (
                    value,
                    product_id,
                ))

        await conn.commit()


# ---------------------------------------------------------
# SUPPORT
# ---------------------------------------------------------

async def create_support_message(user_id, message):
    message = (message or "").strip()

    if not message:
        raise ValueError("EMPTY_MESSAGE")

    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                INSERT INTO support_messages (
                    user_id,
                    message
                )
                VALUES (
                    %s,
                    %s
                )
                RETURNING id
            """, (
                user_id,
                message,
            ))

            sid = (await cur.fetchone())[0]

        await conn.commit()

    return sid


async def latest_support_id(user_id):
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                SELECT id
                FROM support_messages
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT 1
            """, (user_id,))

            row = await cur.fetchone()

            return row[0] if row else None


async def get_support_messages(limit=30):
    p = await _get_pool()

    limit = max(1, min(int(limit), 100))

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                SELECT
                    id,
                    user_id,
                    message,
                    status,
                    created_at
                FROM support_messages
                WHERE status = 'open'
                ORDER BY id DESC
                LIMIT %s
            """, (limit,))

            return await cur.fetchall()


async def reply_support_message(support_id, reply):
    reply = (reply or "").strip()

    if not reply:
        return None

    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                UPDATE support_messages
                SET
                    reply = %s,
                    status = 'replied',
                    replied_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND status = 'open'
                RETURNING user_id
            """, (
                reply,
                support_id,
            ))

            row = await cur.fetchone()

        await conn.commit()

    return row[0] if row else None


# ---------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------

async def stats():
    p = await _get_pool()

    async with p.connection() as conn:
        async with conn.cursor() as cur:

            await cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM users),
                    (SELECT COUNT(*) FROM orders),
                    (
                        SELECT COUNT(*)
                        FROM orders
                        WHERE status = 'approved'
                    ),
                    (
                        SELECT COALESCE(SUM(price), 0)
                        FROM orders
                        WHERE status = 'approved'
                    ),
                    (
                        SELECT COUNT(*)
                        FROM vpn_configs
                        WHERE status = 'available'
                    )
            """)

            row = await cur.fetchone()

    return row
