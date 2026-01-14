import streamlit as st
from src.db import init_db
from src.auth import require_login
from src.ui import (
    render_header,
    page_trader_pricing,
    page_trader_best_prices,
    page_trader_orders,
    page_admin_pricing,
    page_admin_orders,
    page_history
)

st.set_page_config(page_title="Foresight Pricing", layout="wide")
init_db()

if not require_login():
    st.stop()

render_header()

# Navigation (single control)
pages = {
    "Trader | Pricing": page_trader_pricing,
    "Trader | Best Prices": page_trader_best_prices,
    "Trader | Orders": page_trader_orders,
    "History": page_history,
}

if st.session_state.get("role") == "admin":
    pages.update({
        "Admin | Pricing": page_admin_pricing,
        "Admin | Orders": page_admin_orders,
    })

with st.sidebar:
    st.markdown("### Navigation")
    choice = st.radio("", list(pages.keys()), key="nav_choice")

pages[choice]()

# --- Route ---
routes = {
    "Pricing": page_trader_pricing,
    "Best Prices": page_trader_best_prices,
    "Orders": page_trader_orders,
    "History": page_history,
    "Admin Pricing": page_admin_pricing,
    "Admin Orders": page_admin_orders,
}

# If admin radio exists and is selected, use it; otherwise use trader selection
choice = admin_choice if (admin_choice is not None) else trader_choice
routes[choice]()





