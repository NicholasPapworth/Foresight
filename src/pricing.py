import pandas as pd


def apply_margins(prices: pd.DataFrame, margins: pd.DataFrame) -> pd.DataFrame:
    """
    prices must include:
      - Product Category
      - Product
      - Price  (base price)

    margins must include:
      - scope_type ('category'|'product')
      - scope_value
      - margin_per_t

    Rules:
      - product margin overrides category margin
      - margin is hidden from traders; we compute Sell Price only
    """
    df = prices.copy()

    if margins is None or margins.empty:
        df["Sell Price"] = df["Price"].astype(float)
        return df

    cat = margins[margins["scope_type"] == "category"].set_index("scope_value")["margin_per_t"]
    prod = margins[margins["scope_type"] == "product"].set_index("scope_value")["margin_per_t"]

    # Start with category margin (0 if none)
    df["_margin"] = df["Product Category"].map(cat).fillna(0.0)

    # Override with product margin where present
    prod_m = df["Product"].map(prod)
    df.loc[prod_m.notna(), "_margin"] = prod_m[prod_m.notna()]

    df["Sell Price"] = df["Price"].astype(float) + df["_margin"].astype(float)

    return df
