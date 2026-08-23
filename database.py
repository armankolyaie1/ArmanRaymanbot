import os
from contextlib import contextmanager
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=10,
    open=False,
    kwargs={"autocommit": False},
)

def init_db():
    pool.open()
    with pool.connection() as conn:
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
                CREATE TABLE IF NOT EXISTS vpn_configs (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    config TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'available',
                    assigned_order_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    assigned_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id),
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    price BIGINT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_payment',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    amount BIGINT NOT NULL,
                    gateway TEXT,
                    authority TEXT,
                    ref_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    verified_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS support_messages (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id),
                    message TEXT NOT NULL,
                    reply TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    replied_at TIMESTAMP
                )
            """)
            for duration in (1, 3, 6, 12):
                cur.execute("""
                    INSERT INTO products (category,name,duration,price,stock)
                    VALUES ('telegram','تلگرام پریمیوم',%s,0,0)
                    ON CONFLICT (category,duration) DO NOTHING
                """, (duration,))
                cur.execute("""
                    INSERT INTO products (category,name,duration,price,stock)
                    VALUES ('vpn','کانفیگ VLESS',%s,0,0)
                    ON CONFLICT (category,duration) DO NOTHING
                """, (duration,))
            cur.execute("""
                UPDATE products p SET stock=(
                    SELECT COUNT(*) FROM vpn_configs v
                    WHERE v.product_id=p.id AND v.status='available'
                ) WHERE p.category='vpn'
            """)
        conn.commit()

@contextmanager
def get_db():
    with pool.connection() as conn:
        yield conn

def save_user(user):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO users(id,username,first_name) VALUES(%s,%s,%s)
            ON CONFLICT(id) DO UPDATE SET username=EXCLUDED.username, first_name=EXCLUDED.first_name
        """, (user.id,user.username,user.first_name))
        conn.commit()

def get_products(category=None):
    with get_db() as conn:
        if category:
            return conn.execute("SELECT id,category,name,duration,price,stock,active FROM products WHERE category=%s ORDER BY duration",(category,)).fetchall()
        return conn.execute("SELECT id,category,name,duration,price,stock,active FROM products ORDER BY category,duration").fetchall()

def get_product(product_id):
    with get_db() as conn:
        return conn.execute("SELECT id,category,name,duration,price,stock,active FROM products WHERE id=%s",(product_id,)).fetchone()

def create_order(user_id, product_id):
    with get_db() as conn:
        with conn.transaction():
            product = conn.execute("""
                SELECT id,category,name,duration,price,stock,active
                FROM products WHERE id=%s FOR UPDATE
            """,(product_id,)).fetchone()
            if not product: raise ValueError("PRODUCT_NOT_FOUND")
            pid,category,name,duration,price,stock,active=product
            if not active: raise ValueError("PRODUCT_INACTIVE")
            if price <= 0: raise ValueError("PRICE_NOT_SET")
            if category == "vpn":
                available = conn.execute("SELECT COUNT(*) FROM vpn_configs WHERE product_id=%s AND status='available'",(product_id,)).fetchone()[0]
                if available <= 0: raise ValueError("OUT_OF_STOCK")
            elif stock <= 0: raise ValueError("OUT_OF_STOCK")
            order_id=conn.execute("""
                INSERT INTO orders(user_id,product_id,price,status)
                VALUES(%s,%s,%s,'pending_payment') RETURNING id
            """,(user_id,product_id,price)).fetchone()[0]
        return order_id,name,duration,price

def get_user_orders(user_id, limit=20):
    with get_db() as conn:
        return conn.execute("""
            SELECT o.id,p.name,p.duration,o.price,o.status,o.created_at
            FROM orders o JOIN products p ON p.id=o.product_id
            WHERE o.user_id=%s ORDER BY o.id DESC LIMIT %s
        """,(user_id,limit)).fetchall()

def get_order(order_id):
    with get_db() as conn:
        return conn.execute("""
            SELECT o.id,o.user_id,o.product_id,p.category,p.name,p.duration,o.price,o.status,o.created_at
            FROM orders o JOIN products p ON p.id=o.product_id WHERE o.id=%s
        """,(order_id,)).fetchone()

def approve_order(order_id):
    with get_db() as conn:
        with conn.transaction():
            order=conn.execute("""
                SELECT o.id,o.user_id,o.product_id,p.category,o.status
                FROM orders o JOIN products p ON p.id=o.product_id
                WHERE o.id=%s FOR UPDATE
            """,(order_id,)).fetchone()
            if not order: return None,"NOT_FOUND"
            oid,user_id,product_id,category,status=order
            if status!="pending_payment": return None,"NOT_PENDING"
            delivery=None
            if category=="vpn":
                config=conn.execute("""
                    SELECT id,config FROM vpn_configs
                    WHERE product_id=%s AND status='available'
                    ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
                """,(product_id,)).fetchone()
                if not config: return None,"OUT_OF_STOCK"
                config_id,delivery=config
                conn.execute("""
                    UPDATE vpn_configs SET status='assigned',assigned_order_id=%s,assigned_at=CURRENT_TIMESTAMP
                    WHERE id=%s
                """,(order_id,config_id))
            conn.execute("UPDATE orders SET status='approved',updated_at=CURRENT_TIMESTAMP WHERE id=%s",(order_id,))
            if category=="vpn":
                conn.execute("""
                    UPDATE products SET stock=(SELECT COUNT(*) FROM vpn_configs
                    WHERE product_id=products.id AND status='available') WHERE id=%s
                """,(product_id,))
        return delivery,"OK"

def reject_order(order_id):
    with get_db() as conn:
        result=conn.execute("""
            UPDATE orders SET status='rejected',updated_at=CURRENT_TIMESTAMP
            WHERE id=%s AND status='pending_payment' RETURNING id,user_id
        """,(order_id,)).fetchone()
        conn.commit()
        return result

def add_vpn_config(product_id, config):
    config=config.strip()
    if not config: raise ValueError("EMPTY_CONFIG")
    with get_db() as conn:
        with conn.transaction():
            cid=conn.execute("INSERT INTO vpn_configs(product_id,config) VALUES(%s,%s) RETURNING id",(product_id,config)).fetchone()[0]
            conn.execute("""
                UPDATE products SET stock=(SELECT COUNT(*) FROM vpn_configs
                WHERE product_id=products.id AND status='available') WHERE id=%s
            """,(product_id,))
        return cid

def get_vpn_inventory():
    with get_db() as conn:
        return conn.execute("""
            SELECT v.id,p.name,p.duration,v.status,v.created_at
            FROM vpn_configs v JOIN products p ON p.id=v.product_id
            ORDER BY v.id DESC LIMIT 50
        """).fetchall()

def get_admin_orders(limit=30):
    with get_db() as conn:
        return conn.execute("""
            SELECT o.id,o.user_id,p.name,p.duration,o.price,o.status,o.created_at
            FROM orders o JOIN products p ON p.id=o.product_id
            ORDER BY o.id DESC LIMIT %s
        """,(limit,)).fetchall()

def update_product_value(product_id, field, value):
    if field not in ("price","stock","active"): raise ValueError("INVALID_FIELD")
    with get_db() as conn:
        if field=="price":
            conn.execute("UPDATE products SET price=%s WHERE id=%s",(value,product_id))
        elif field=="stock":
            conn.execute("UPDATE products SET stock=%s WHERE id=%s AND category<>'vpn'",(value,product_id))
        else:
            conn.execute("UPDATE products SET active=%s WHERE id=%s",(value,product_id))
        conn.commit()

def add_support_message(user_id, message):
    with get_db() as conn:
        conn.execute("INSERT INTO support_messages(user_id,message) VALUES(%s,%s)",(user_id,message))
        conn.commit()

def stats():
    with get_db() as conn:
        users=conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        orders=conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        approved=conn.execute("SELECT COUNT(*) FROM orders WHERE status='approved'").fetchone()[0]
        revenue=conn.execute("SELECT COALESCE(SUM(price),0) FROM orders WHERE status='approved'").fetchone()[0]
        vpn_available=conn.execute("SELECT COUNT(*) FROM vpn_configs WHERE status='available'").fetchone()[0]
        return users,orders,approved,revenue,vpn_available
