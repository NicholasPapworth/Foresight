# app.py
import os
import io
import uuid
import time
import hashlib
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

# -----------------------------
# Config
# -----------------------------
APP_TITLE = "Trading Price Sheet"
DB_PATH = "prices.db"
LOGO_PATH = "assets/logo.svg"
REQUIRED_COLS = ["Product Category", "Product", "Location", "Price"]

# -----------------------------
# Basic styling (corporate, restrained)
# -----------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide")

st.markdown(
    """
    <style>
      .app-header { display:flex; align-items:center; justify-content:space-between; padding: 8px 0 14px 0; }
      .app-title { font-size: 20px; font-weight: 600; letter-spacing: 0.2px; }
      .meta { font-size: 12px; color: #6b7280; }
      .card { border: 1px solid #e5e7eb; border-radius: 14px; padding: 14px 16px; background: #ffffff; }
      .stDataFrame { border-radius: 12px; overflow: hidden; }
      section[data-testid="stSidebar"] { border-right: 1px solid #e5e7eb; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# DB helpers
# -----------------------------
def db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            snapshot_id TEXT PRIMARY KEY,
            published_at_utc TEXT NOT NULL,
            published_by TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            row_count INTEGER NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            snapshot_id TEXT NOT NULL,
            product_category TEXT NOT NULL,
            product TEXT NOT NULL,
            location TEXT NOT NULL,
            price REAL NOT NULL,
            currency TEXT,
            PRIMARY KEY (snapshot_id, product_category, product, location),
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
        );
    """)
    conn.commit()
    conn.close()

def latest_snapshot():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT snapshot_id, published_at_utc, published_by
        FROM snapshots
        ORDER BY published_at_utc DESC
        LIMIT 1;
    """)
    row = cur.fetchone()
    conn.close()
    return row  # (id, ts, by) or None

def list_snapshots(limit=200):
    conn = db_conn()
    df = pd.read_sql_query(
        f"""
        SELECT snapshot_id, published_at_utc, published_by, row_count
        FROM snapshots
        ORDER BY published_at_utc DESC
        LIMIT {int(limit)};
        """,
        conn
    )
    conn.close()
    return df

def load_prices(snapshot_id: str) -> pd.DataFrame:
    conn = db_conn()
    df = pd.read_sql_query(
        """
        SELECT
            product_category AS "Product Category",
            product AS "Product",
            location AS "Location",
            price AS "Price",
            currency AS "Currency"
        FROM prices
        WHERE snapshot_id = ?
        ORDER BY product_category, product, location;
        """,
        conn,
        params=(snapshot_id,)
    )
    conn.close()
    return df

def publish_snapshot(prices_df: pd.DataFrame, published_by: str, source_bytes: bytes) -> str:
    # Normalize columns
    df = prices_df.copy()
    df = df.rename(columns={
        "Product Category": "product_category",
        "Product": "product",
        "Location": "location",
        "Price": "price"
    })

    # Basic validation
    missing = [c for c in ["product_category", "product", "location", "price"] if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["price"] = pd.to_numeric(df["price"], errors="raise")
    df["product_category"] = df["product_category"].astype(str).str.strip()
    df["product"] = df["product"].astype(str).str.strip()
    df["location"] = df["location"].astype(str).str.strip()

    # Optional currency
    currency = None
    if "Currency" in prices_df.columns:
        currency = prices_df["Currency"].astype(str).fillna("").iloc[0] if len(prices_df) else ""
    df["currency"] = currency

    # Snapshot metadata
    snapshot_id = str(uuid.uuid4())
    published_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    row_count = int(len(df))

    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO snapshots (snapshot_id, published_at_utc, published_by, source_hash, row_count)
        VALUES (?, ?, ?, ?, ?);
    """, (snapshot_id, published_at, published_by, source_hash, row_count))

    # Insert rows
    rows = list(df[["product_category", "product", "location", "price", "currency"]].itertuples(index=False, name=None))
    cur.executemany("""
        INSERT INTO prices (snapshot_id, product_category, product, location, price, currency)
        VALUES (?, ?, ?, ?, ?, ?);
    """, [(snapshot_id, *r) for r in rows])

    conn.commit()
    conn.close()
    return snapshot_id

# -----------------------------
# Auth (Option 2 - simple)
# In production: store users in DB + bcrypt hashes.
# For now: st.secrets (safe) or env variables.
# -----------------------------
def require_login():
    if "user" not in st.session_state:
        st.session_state.user = None
        st.session_state.role = None

    if st.session_state.user:
        return True

    st.markdown("### Sign in")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    # Example: use st.secrets
    # st.secrets["users"] = {"alice": {"password": "x", "role":"admin"}, ...}
    users = st.secrets.get("users", {}) if hasattr(st, "secrets") else {}

    if st.button("Sign in", use_container_width=True):
        u = users.get(username)
        if not u or u.get("password") != password:
            st.error("Invalid credentials.")
        else:
            st.session_state.user = username
            st.session_state.role = u.get("role", "trader")
            st.rerun()

    st.info("Admins can publish. Traders are read-only.")
    return False

# -----------------------------
# App
# -----------------------------
init_db()

if not require_login():
    st.stop()

# Header
left, mid, right = st.columns([2, 5, 3], vertical_alignment="center")
with left:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=170)
    else:
        st.caption("Upload your logo to: assets/logo.png")

with mid:
    st.markdown(f"<div class='app-title'>{APP_TITLE}</div>", unsafe_allow_html=True)

with right:
    latest = latest_snapshot()
    if latest:
        sid, ts, by = latest
        st.markdown(f"<div class='meta'>Live snapshot: <b>{ts}</b><br/>Published by: <b>{by}</b></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='meta'>No snapshot published yet.</div>", unsafe_allow_html=True)

st.divider()

tab_live, tab_history, tab_admin = st.tabs(["Live Prices", "History", "Admin"])

# Sidebar controls
with st.sidebar:
    st.markdown("#### Search & Filters")
    q = st.text_input("Search (category / product / location)", placeholder="e.g. AN, Teesside, 34.5, etc.")
    st.markdown("---")
    auto_refresh = st.toggle("Auto-refresh live view", value=False)
    refresh_seconds = st.number_input("Refresh interval (seconds)", min_value=10, max_value=600, value=60, step=10)

# Live
with tab_live:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    latest = latest_snapshot()
    if not latest:
        st.warning("No live data yet. Admin must publish the first snapshot.")
    else:
        sid, ts, by = latest
        df = load_prices(sid)

        # Search
        if q:
            q_lower = q.lower()
            mask = (
                df["Product Category"].astype(str).str.lower().str.contains(q_lower, na=False)
                | df["Product"].astype(str).str.lower().str.contains(q_lower, na=False)
                | df["Location"].astype(str).str.lower().str.contains(q_lower, na=False)
                | df["Price"].astype(str).str.lower().str.contains(q_lower, na=False)
            )
            df = df[mask]

        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"Snapshot ID: {sid}")

    st.markdown("</div>", unsafe_allow_html=True)

    # Auto-refresh (optional)
    if auto_refresh:
        time.sleep(int(refresh_seconds))
        st.rerun()

# History
with tab_history:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    snaps = list_snapshots()
    if snaps.empty:
        st.info("No snapshots available yet.")
    else:
        snaps["label"] = snaps["published_at_utc"] + "  |  " + snaps["published_by"] + "  |  " + snaps["snapshot_id"].str.slice(0, 8)
        selected = st.selectbox("Select a snapshot", snaps["label"].tolist())
        sel_row = snaps[snaps["label"] == selected].iloc[0]
        sel_id = sel_row["snapshot_id"]

        df_hist = load_prices(sel_id)

        if q:
            q_lower = q.lower()
            mask = (
                df_hist["Product Category"].astype(str).str.lower().str.contains(q_lower, na=False)
                | df_hist["Product"].astype(str).str.lower().str.contains(q_lower, na=False)
                | df_hist["Location"].astype(str).str.lower().str.contains(q_lower, na=False)
                | df_hist["Price"].astype(str).str.lower().str.contains(q_lower, na=False)
            )
            df_hist = df_hist[mask]

        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        st.caption(f"As-of: {sel_row['published_at_utc']} (UTC) | Snapshot ID: {sel_id}")

    st.markdown("</div>", unsafe_allow_html=True)

# Admin
with tab_admin:
    if st.session_state.role != "admin":
        st.warning("Admin access required.")
    else:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("#### Publish a new snapshot")
        uploaded = st.file_uploader("Upload Excel price sheet", type=["xlsx"])

        if uploaded is not None:
            content = uploaded.read()
            try:
                xls = pd.ExcelFile(io.BytesIO(content))
                # Assumption: first sheet contains the price table
                sheet = xls.sheet_names[0]
                df_in = pd.read_excel(io.BytesIO(content), sheet_name=sheet)

                # Validate columns
                missing = [c for c in REQUIRED_COLS if c not in df_in.columns]
                if missing:
                    st.error(f"Missing required columns: {missing}")
                else:
                    st.success("File structure looks valid. Preview below.")
                    st.dataframe(df_in[REQUIRED_COLS].head(50), use_container_width=True, hide_index=True)

                    if st.button("Publish snapshot", type="primary", use_container_width=True):
                        snapshot_id = publish_snapshot(df_in[REQUIRED_COLS], st.session_state.user, content)
                        st.success(f"Published. Snapshot ID: {snapshot_id}")
                        st.rerun()

            except Exception as e:
                st.error(f"Failed to process Excel: {e}")

        st.markdown("</div>", unsafe_allow_html=True)

