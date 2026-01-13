import io
import pandas as pd

REQUIRED = ["Supplier", "Product", "Location", "Delivery Window", "Price", "Unit"]
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

    # Clean fields
    for c in ["Supplier", "Product", "Location", "Delivery Window", "Unit"]:
        df[c] = df[c].astype(str).str.strip()

    df["Price"] = pd.to_numeric(df["Price"], errors="raise")
    df = df.dropna(subset=["Supplier", "Product", "Location", "Delivery Window", "Price", "Unit"])

    # Optional column
    if "Product Category" not in df.columns:
        df["Product Category"] = ""

    dup = df.duplicated(subset=UNIQUE_KEY, keep=False)
    if dup.any():
        bad = df.loc[dup, UNIQUE_KEY]
        raise ValueError("Duplicate rows found for key (Supplier+Product+Location+Delivery Window). Fix:\n"
                         f"{bad.head(50)}")

    return df[["Supplier", "Product Category", "Product", "Location", "Delivery Window", "Price", "Unit"]]
