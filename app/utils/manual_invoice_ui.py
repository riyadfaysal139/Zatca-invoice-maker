import streamlit as st
import pandas as pd
import os
import sqlite3
from datetime import datetime
from types import SimpleNamespace

from pdf_creator import PDFCreator
from datetime import datetime, timedelta

def get_day(date_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%A")

def get_date(days=0, specific_date=None):
    if specific_date:
        base = datetime.strptime(specific_date, "%Y-%m-%d")
    else:
        base = datetime.today()
    return (base + timedelta(days=days)).strftime("%Y-%m-%d")


st.set_page_config(page_title="Manual Invoice Creator", layout="centered")
st.title("🧾 Manual Invoice Creator")

# --- Utility Functions ---
def safe_float(val):
    try:
        return round(float(str(val).replace(',', '').strip()), 2)
    except:
        return 0.0

def load_mapping(file_path):
    mapping = {}
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) == 2:
                    key, value = parts
                    mapping[key.strip()] = value.strip()
    return mapping

# --- Load mappings ---
description_map = load_mapping("files/Texts/description_mapping.txt")
arabic_map = load_mapping("files/Texts/arabic_description_mapping.txt")
name_map = load_mapping("files/Texts/name_mapping.txt")

# --- Invoice Metadata Input ---
po_number = st.text_input("PO Number", value="Manual001")
po_date = st.date_input("PO Date")
invoice_date = st.date_input("Invoice Date (ignored for PDF; calculated as PO + 1 day)")

shop_options = list(name_map.values())
shop_options = ["-- Select --"] + list(name_map.values())
shop_name = st.selectbox("Shop Name", shop_options)

if shop_name == "-- Select --":
    st.warning("⚠️ Please select a valid shop name.")

# --- Product Table ---
st.markdown("### Product Table")

def get_default_table():
    rows = []
    for sku in sorted([k for k in description_map.keys() if k.isdigit()], key=lambda x: int(x)):
        rows.append({
            "SKU": sku,
            "Description": description_map.get(sku, ""),
            "Arabic Description": arabic_map.get(sku, ""),
            "Unit Price": 0,
            "Quantity": 0
        })
    return pd.DataFrame(rows)

if "products" not in st.session_state:
    st.session_state.products = get_default_table().to_dict("records")

# --- Show Product Editor ---
df_with_calculations = pd.DataFrame(st.session_state.products)
df_with_calculations["Unit Price"] = pd.to_numeric(df_with_calculations["Unit Price"], errors="coerce").fillna(0)
df_with_calculations["Quantity"] = pd.to_numeric(df_with_calculations["Quantity"], errors="coerce").fillna(0)
df_with_calculations["Price"] = df_with_calculations["Unit Price"] * df_with_calculations["Quantity"]
df_with_calculations["Vat"] = (df_with_calculations["Price"] * 0.15).round(2)
df_with_calculations["Amount"] = (df_with_calculations["Price"] + df_with_calculations["Vat"]).round(2)

with st.form("product_form"):
    edited_df = st.data_editor(
        df_with_calculations,
        use_container_width=True,
        num_rows="dynamic",
        key="product_editor"
    )
    calculate = st.form_submit_button("🧮 Calculate Totals")
    if calculate:
        st.session_state.products = edited_df.to_dict("records")
        df_with_calculations = pd.DataFrame(st.session_state.products)
        df_with_calculations["Unit Price"] = pd.to_numeric(df_with_calculations["Unit Price"], errors="coerce").fillna(0)
        df_with_calculations["Quantity"] = pd.to_numeric(df_with_calculations["Quantity"], errors="coerce").fillna(0)
        df_with_calculations["Price"] = df_with_calculations["Unit Price"] * df_with_calculations["Quantity"]
        df_with_calculations["Vat"] = (df_with_calculations["Price"] * 0.15).round(2)
        df_with_calculations["Amount"] = (df_with_calculations["Price"] + df_with_calculations["Vat"]).round(2)

        total_qty = int(df_with_calculations["Quantity"].sum())
        total_price = round(float(df_with_calculations["Price"].sum()), 2)
        total_vat = round(float(df_with_calculations["Vat"].sum()), 2)
        total_amt = round(float(df_with_calculations["Amount"].sum()), 2)

        st.markdown("### 💵 Invoice Summary")
        st.write(f"**Total Quantity:** {total_qty}")
        st.write(f"**Total (ex. VAT):** {total_price:.2f} SAR")
        st.write(f"**VAT (15%):** {total_vat:.2f} SAR")
        st.write(f"**Total (inc. VAT):** {total_amt:.2f} SAR")


# --- Add New Row ---
if st.button("➕ Add Row"):
    st.session_state.products.append({
        "SKU": "", "Description": "", "Arabic Description": "",
        "Unit Price": 0.0, "Quantity": 0
    })
    st.rerun()

# --- Save and Generate Invoice ---
if st.button("✅ Create Invoice"):
    try:
        df_clean = pd.DataFrame(st.session_state.products).dropna(subset=["SKU", "Unit Price", "Quantity"])
        products = df_clean.to_dict(orient="records")

        if not products:
            st.error("❌ Please add at least one valid product row.")
        elif shop_name == "-- Select --":
            st.error("❌ Shop name is required. Please select a valid shop.")
        else:
            db_path = "files/DB/downloaded_files.db"
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Create po_metadata table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS po_metadata (
                    po_number TEXT PRIMARY KEY,
                    po_release_date TEXT,
                    supplier_name TEXT,
                    buyer TEXT,
                    ship_to TEXT,
                    supplier_vat TEXT,
                    shop_vat TEXT,
                    expected_receiving_date TEXT,
                    cancellation_date TEXT,
                    total_quantity INTEGER,
                    total_price REAL,
                    total_vat REAL,
                    total_amount REAL,
                    file_name TEXT
                )
            ''')

            # Totals
            total_qty = sum(int(p["Quantity"]) for p in products)
            total_price = sum(float(p["Unit Price"] or 0) * int(p["Quantity"] or 0) for p in products)
            total_vat = round(total_price * 0.15, 4)
            total_amt = round(total_price + total_vat, 4)

            # Save metadata
            cursor.execute("""
                INSERT OR REPLACE INTO po_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                po_number,
                str(po_date),
                "337337 FAKHR ALTASHYEED EST.",
                "SOU Vegetable for South",
                shop_name,
                "301308065300003",
                "310072568710003",
                str(po_date),
                str(po_date),
                total_qty,
                round(total_price, 2),
                total_vat,
                total_amt,
                f"{po_number}_{shop_name.replace(' ', '_')}.pdf"
            ))

            # Save item table
            table_name = f"po_{po_number}"
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {table_name} (
                    SKU TEXT,
                    Description TEXT,
                    [Unit Price] REAL,
                    Quantity INTEGER,
                    Price REAL,
                    Vat REAL,
                    Amount REAL
                )
            ''')
            cursor.execute(f'DELETE FROM {table_name}')
            for row in products:
                quantity = int(row.get("Quantity", 0))
                if quantity <= 0:
                    continue  # 🚫 Skip products with 0 quantity

                unit_price = float(row.get("Unit Price", 0))
                price = round(unit_price * quantity, 2)
                vat = round(price * 0.15, 2)
                amount = round(price + vat, 2)

                cursor.execute(f'''
                    INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row.get("SKU", ""),
                    row.get("Description", ""),
                    unit_price,
                    quantity,
                    price,
                    vat,
                    amount
                ))


            conn.commit()
            conn.close()

            # 📅 Generate invoice using po_date + 1 logic
            invoice_date_str = get_date(1, str(po_date))
            po_day = get_day(str(po_date))
            invoice_day = get_day(invoice_date_str)

            session = SimpleNamespace(
                po_date=str(po_date),
                invoice_date=invoice_date_str,
                po_day=po_day,
                invoice_day=invoice_day
            )

            pdf_creator = PDFCreator(session)
            pdf_creator.generate_invoice_for(po_number)

            st.success(f"✅ Invoice created and PDF generated for PO {po_number} on {invoice_date_str}!")

    except Exception as e:
        st.error(f"❌ Error: {e}")
