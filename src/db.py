import sqlite3
import pandas as pd
from datetime import datetime, timezone
import hashlib
import uuid

DB_PATH = "foresight.db"

def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL;")
    return c

def init_db():
    c = conn()
    cur = c.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS supplier_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        published_at_utc TEXT NOT NULL,
        published_by TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        row_count INTEGER NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS supplier_prices (
        snapshot_id TEXT NOT NULL,
        supplier TEXT NOT NULL,
        product_category TEXT,
        product TEXT NOT NULL,
        location TEXT NOT NULL,
        delivery_window TEXT NOT NULL,
        price REAL NOT NULL,
        unit TEXT NOT NULL,
        PRIMARY KEY (snapshot_id, supplier, product, location, delivery_window),
        FOREIGN KEY (snapshot_id) REFERENCES supplier_snapshots(snapshot_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # Defaults
    _set_default(cur, "small_lot_threshold_t", "24")
    _set_default(cur, "small_lot_charge_per_t", "15")
    _set_default(cur, "basket_timeout_minutes", "20")

    c.commit()
    c.close()

def _set_default(cur, key, value):
    cur.execute("SELECT 1 FROM app_settings WHERE key = ?", (key,))
    if not cur.fetchone():
        cur.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", (key, value))

def get_settings() -> dict:
    c = conn()
    df = pd.read_sql_query("SELECT key, value FROM app_settings", c)
    c.close()
    return {r["key"]: r["value"] for _, r in df.iterrows()}

def set_setting(key: str, value: str):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, value))
    c.commit()
    c.close()

def list_supplier_snapshots(limit=200) -> pd.DataFrame:
    c = conn()
    df = pd.read_sql_query(f"""
        SELECT snapshot_id, published_at_utc, published_by, row_count
        FROM supplier_snapshots
        ORDER BY published_at_utc DESC
        LIMIT {int(limit)}
    """, c)
    c.close()
    return df

def latest_supplier_snapshot():
    c = conn()
    cur = c.cursor()
    cur.execute("""
        SELECT snapshot_id, published_at_utc, published_by
        FROM supplier_snapshots
        ORDER BY published_at_utc DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    c.close()
    return row

def load_supplier_prices(snapshot_id: str) -> pd.DataFrame:
    c = conn()
    df = pd.read_sql_query("""
        SELECT
          supplier AS "Supplier",
          product_category AS "Product Category",
          product AS "Product",
          location AS "Location",
          delivery_window AS "Delivery Window",
          price AS "Price",
          unit AS "Unit"
        FROM supplier_prices
        WHERE snapshot_id = ?
        ORDER BY supplier, product, location, delivery_window
    """, c, params=(snapshot_id,))
    c.close()
    return df

def publish_supplier_snapshot(df: pd.DataFrame, published_by: str, source_bytes: bytes) -> str:
    snapshot_id = str(uuid.uuid4())
    published_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    row_count = int(len(df))

    c = conn()
    cur = c.cursor()

    cur.execute("""
        INSERT INTO supplier_snapshots (snapshot_id, published_at_utc, published_by, source_hash, row_count)
        VALUES (?, ?, ?, ?, ?)
    """, (snapshot_id, published_at, published_by, source_hash, row_count))

    rows = []
    for r in df.itertuples(index=False):
        rows.append((
            snapshot_id,
            str(r.Supplier).strip(),
            str(getattr(r, "Product Category", "")).strip() if "Product Category" in df.columns else "",
            str(r.Product).strip(),
            str(r.Location).strip(),
            str(r._asdict().get("Delivery Window", "")).strip(),
            float(r.Price),
            str(r.Unit).strip(),
        ))

    cur.executemany("""
        INSERT INTO supplier_prices
        (snapshot_id, supplier, product_category, product, location, delivery_window, price, unit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    c.commit()
    c.close()
    return snapshot_id
