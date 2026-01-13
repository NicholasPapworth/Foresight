import io
import time
import streamlit as st
import pandas as pd

from src.db import (
    get_settings, set_setting,
    latest_supplier_snapshot, list_supplier_snapshots,
    load_supplier_prices, publish_supplier_snapshot
)
from src.validation import load_supplier_sheet
from src.optimizer import optimise_basket

LOGO_PATH = "assets/logo.svg"

def render_header():
    left, mid, right = st.columns([2, 5, 3], vertical_alignment="center")
    with left:
        try:
            st.image(LOGO_PATH, width=170)
        except Exception:
            st.caption("Logo missing.")
    with mid:
        st.markdown("## Foresight Pricing")
    with right:
        snap = latest_supplier_snapshot()
        if snap:
            sid, ts, by = snap
            st.caption(f"Latest supplier snapshot: {ts} UTC\nPublished by: {by}")
        else:
            st.caption("No supplier snapshot published yet.")
    st.divider()

def _get_latest_prices_df():
    snap = latest_supplier_snapshot()
    if not snap:
        return None, None
    sid, ts, by = snap
    df = load_supplier_prices(sid)
    return sid, df

def page_admin():
    if st.session_state.role != "admin":
        st.warning("Admin access required.")
        return

    st.subheader("Admin")

    settings = get_settings()
    c1, c2, c3 = st.columns(3)
    with c1:
        lot_charge = st.number_input("Small-lot charge (£/t)", min_value=0.0, value=float(settings["small_lot_charge_per_t"]))
    with c2:
        threshold = st.number_input("Small-lot threshold (t)", min_value=1.0, value=float(settings["small_lot_threshold_t"]))
    with c3:
        timeout = st.number_input("Basket timeout (minutes)", min_value=1, value=int(settings["basket_timeout_minutes"]))

    if st.button("Save settings", use_container_width=True):
        set_setting("small_lot_charge_per_t", str(lot_charge))
        set_setting("small_lot_threshold_t", str(threshold))
        set_setting("basket_timeout_minutes", str(timeout))
        st.success("Settings saved.")

    st.divider()
    st.markdown("### Upload supplier prices (SUPPLIER_PRICES)")
    up = st.file_uploader("Upload Excel", type=["xlsx"])

    if up:
        content = up.read()
        try:
            df = load_supplier_sheet(content)
            st.success("Validated. Preview:")
            st.dataframe(df, use_container_width=True, hide_index=True)

            if st.button("Publish supplier snapshot", type="primary", use_container_width=True):
                sid = publish_supplier_snapshot(df, st.session_state.user, content)
                st.success(f"Published supplier snapshot: {sid}")
                st.rerun()
        except Exception as e:
            st.error(str(e))

def page_history():
    st.subheader("History")
    snaps = list_supplier_snapshots()
    if snaps.empty:
        st.info("No snapshots yet.")
        return

    snaps["label"] = snaps["published_at_utc"] + " | " + snaps["published_by"] + " | " + snaps["snapshot_id"].str[:8]
    label = st.selectbox("Select snapshot", snaps["label"].tolist())
    sid = snaps.loc[snaps["label"] == label, "snapshot_id"].iloc[0]
    df = load_supplier_prices(sid)

    q = st.text_input("Search")
    if q:
        ql = q.lower()
        df = df[df.apply(lambda r: any(ql in str(v).lower() for v in r.values), axis=1)]

    st.dataframe(df, use_container_width=True, hide_index=True)

def page_trader():
    st.subheader("Trader")

    sid, df = _get_latest_prices_df()
    if df is None:
        st.warning("No supplier snapshot available. Admin must publish one.")
        return

    settings = get_settings()
    lot_charge = float(settings["small_lot_charge_per_t"])
    threshold = float(settings["small_lot_threshold_t"])
    timeout_min = int(settings["basket_timeout_minutes"])

    # Basket state
    if "basket" not in st.session_state:
        st.session_state.basket = []
        st.session_state.basket_created_at = time.time()

    # Expiry
    age_sec = time.time() - st.session_state.basket_created_at
    if age_sec > timeout_min * 60:
        st.session_state.basket = []
        st.session_state.basket_created_at = time.time()
        st.info("Basket expired and has been cleared.")

    st.caption(f"Using supplier snapshot: {sid[:8]} | Basket timeout: {timeout_min} min | Small-lot: < {threshold}t charged at £{lot_charge}/t")

    # Controls
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    with c1:
        product = st.selectbox("Product", sorted(df["Product"].unique()))
    with c2:
        location = st.selectbox("Location", sorted(df["Location"].unique()))
    with c3:
        window = st.selectbox("Delivery Window", sorted(df["Delivery Window"].unique()))
    with c4:
        qty = st.number_input("Qty (t)", min_value=0.0, value=10.0, step=1.0)

    if st.button("Add to basket", use_container_width=True):
        st.session_state.basket.append({
            "Product": product,
            "Location": location,
            "Delivery Window": window,
            "Qty": float(qty),
        })
        st.rerun()

    # Basket table
    if st.session_state.basket:
        bdf = pd.DataFrame(st.session_state.basket)
        st.markdown("### Basket")
        st.dataframe(bdf, use_container_width=True, hide_index=True)

        if st.button("Clear basket"):
            st.session_state.basket = []
            st.session_state.basket_created_at = time.time()
            st.rerun()

        if st.button("Optimise", type="primary", use_container_width=True):
            res = optimise_basket(
                supplier_prices=df[["Supplier","Product","Location","Delivery Window","Price"]],
                basket=st.session_state.basket,
                small_lot_threshold_t=threshold,
                small_lot_charge_per_t=lot_charge
            )
            if not res["ok"]:
                st.error(res["error"])
                return

            st.markdown("### Optimal allocation")
            st.dataframe(pd.DataFrame(res["allocation"]), use_container_width=True, hide_index=True)

            if res["lot_charges"]:
                st.markdown("### Small-lot charges")
                st.dataframe(pd.DataFrame(res["lot_charges"]), use_container_width=True, hide_index=True)

            st.markdown("### Totals")
            st.write({
                "Base cost": res["base_cost"],
                "Small-lot total": res["lot_charge_total"],
                "Grand total": res["total"],
            })
    else:
        st.info("Basket is empty.")
