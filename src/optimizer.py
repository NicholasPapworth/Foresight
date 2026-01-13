from itertools import combinations
import pandas as pd

def tier_charge_per_t(tonnes: float, tiers: pd.DataFrame) -> float:
    t = float(tonnes)
    if t <= 0:
        return 0.0

    active = tiers[tiers["active"] == 1].copy()
    active = active.sort_values("min_t")

    for r in active.to_dict("records"):
        mn = float(r["min_t"])
        mx = r.get("max_t", None)
        mx = None if mx is None or (isinstance(mx, float) and pd.isna(mx)) else float(mx)

        if t >= mn and (mx is None or t <= mx):
            return float(r["charge_per_t"])

    return 0.0

def optimise_basket(
    supplier_prices: pd.DataFrame,
    basket: list[dict],
    tiers: pd.DataFrame
) -> dict:

    """
    supplier_prices columns: Supplier, Product, Location, Delivery Window, Price
    basket: [{Product, Location, Delivery Window, Qty}]
    No split per line.
    """

    if not basket:
        return {"ok": False, "error": "Basket is empty."}

    # Build per-line candidate suppliers
    candidates_by_line = []
    all_suppliers = set()

    for line in basket:
        prod = line["Product"]
        loc = line["Location"]
        win = line["Delivery Window"]

        subset = supplier_prices[
            (supplier_prices["Product"] == prod) &
            (supplier_prices["Location"] == loc) &
            (supplier_prices["Delivery Window"] == win)
        ][["Supplier", "Price"]].copy()

        if subset.empty:
            return {"ok": False, "error": f"No supplier prices for {prod} @ {loc} {win}"}

        subset = subset.sort_values("Price", ascending=True)
        cands = subset["Supplier"].tolist()
        candidates_by_line.append((line, subset))
        all_suppliers.update(cands)

    all_suppliers = sorted(all_suppliers)
    k = len(all_suppliers)

    # Prune for speed: keep only suppliers that appear in top N for any line
    # (optional; safe)
    # N = min(10, k)

    best = None

    # Enumerate subsets of suppliers
    for r in range(1, min(k, 15) + 1):  # hard cap for safety; tune later
        for S in combinations(all_suppliers, r):
            S = set(S)

            allocation = []
            tonnes_by_supplier = {s: 0.0 for s in S}
            base_cost = 0.0

            feasible = True
            for line, subset in candidates_by_line:
                # choose cheapest supplier in S for this line
                sub2 = subset[subset["Supplier"].isin(S)]
                if sub2.empty:
                    feasible = False
                    break
                chosen = sub2.iloc[0]
                s = chosen["Supplier"]
                price = float(chosen["Price"])
                qty = float(line["Qty"])

                allocation.append({
                    "Product": line["Product"],
                    "Location": line["Location"],
                    "Delivery Window": line["Delivery Window"],
                    "Qty": qty,
                    "Supplier": s,
                    "Price": price,
                    "Line Cost": qty * price
                })

                tonnes_by_supplier[s] += qty
                base_cost += qty * price

            if not feasible:
                continue

            # Tiered small-lot charges per supplier
            lot_charge_total = 0.0
            lot_charges = []
            for s, t in tonnes_by_supplier.items():
                if t <= 0:
                    continue
                cpt = tier_charge_per_t(t, tiers)
                if cpt > 0:
                    c = t * cpt
                    lot_charge_total += c
                    lot_charges.append({
                        "Supplier": s,
                        "Tonnes": t,
                        "Charge £/t": cpt,
                        "Lot Charge": c
                    })

            total = base_cost + lot_charge_total

            if best is None or total < best["total"]:
                best = {
                    "total": total,
                    "base_cost": base_cost,
                    "lot_charge_total": lot_charge_total,
                    "allocation": allocation,
                    "lot_charges": lot_charges
                }

    if best is None:
        return {"ok": False, "error": "No feasible supplier set found."}

    return {"ok": True, **best}
