import io
import pandas as pd

REQUIRED = ["Supplier", "Product", "Delivery Window", "Price", "Unit"]
OPTIONAL = ["Location", "Product Category"]
SHEET = "SUPPLIER_PRICES"
UNIQUE_KEY = ["Supplier", "Product", "Location", "Delivery Window"]

def load_supplier_sheet(content: bytes) -> pd.DataFrame:
    xls = pd.ExcelFile(io.BytesIO(content))
    if SHEET not in xls.sheet_names:
        raise ValueError(f"Workbook must contain a sheet named '{SHEET}'. Found: {xls.sheet_names}")

    df = pd.read_excel(io.BytesIO(content), sheet_name=SHEET)
    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Ensure optional columns exist
    if "Location" not in df.columns:
        df["Location"] = ""
    if "Product Category" not in df.columns:
        df["Product Category"] = ""

    # Clean string fields (preserve blanks properly)
    def _clean_str(s: pd.Series) -> pd.Series:
        return s.fillna("").astype(str).str.strip()

    for c in ["Supplier", "Product", "Location", "Delivery Window", "Unit", "Product Category"]:
        df[c] = _clean_str(df[c])

    # Price numeric
    df["Price"] = pd.to_numeric(df["Price"], errors="raise")

    # Drop rows missing critical required values (Location is allowed to be blank)
    df = df.dropna(subset=["Price"])
    df = df[(df["Supplier"] != "") & (df["Product"] != "") & (df["Delivery Window"] != "") & (df["Unit"] != "")]

    # Optional: if you want blanks to become "National", uncomment:
    # df.loc[df["Location"] == "", "Location"] = "National"

    dup = df.duplicated(subset=UNIQUE_KEY, keep=False)
    if dup.any():
        bad = df.loc[dup, UNIQUE_KEY]
        raise ValueError(
            "Duplicate rows found for key (Supplier+Product+Location+Delivery Window). Fix:\n"
            f"{bad.head(50)}"
        )

    return df[["Supplier", "Product Category", "Product", "Location", "Delivery Window", "Price", "Unit"]]

