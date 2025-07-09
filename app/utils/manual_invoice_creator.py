import sqlite3
import pandas as pd
from fpdf import FPDF
import os
import qrcode
import codecs
import arabic_reshaper
from bidi.algorithm import get_display

def create_manual_invoice(po_number, invoice_date, po_date, products, output_path, shop_name="Manual Location"):
    db_path = "files/DB/downloaded_files.db"
    description_mapping = {}
    arabic_description_mapping = {}

    # Load mappings
    def load_mapping(file_path):
        mapping = {}
        if not os.path.exists(file_path):
            return mapping
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) == 2:
                    key, value = parts
                    mapping[key.strip()] = value.strip()
        return mapping

    description_mapping = load_mapping('files/Texts/description_mapping.txt')
    arabic_description_mapping = load_mapping('files/Texts/arabic_description_mapping.txt')

    # Convert product list to dataframe
    df = pd.DataFrame(products, columns=["SKU", "Description", "Unit Price", "Quantity"])
    df["Price"] = df["Unit Price"] * df["Quantity"]
    df["Vat"] = (df["Price"] * 0.15).round(4)
    df["Amount"] = (df["Price"] + df["Vat"]).round(4)

    total_row = pd.DataFrame([["", "Total", "", df["Quantity"].sum(), df["Price"].sum(), df["Vat"].sum(), df["Amount"].sum()]],
                             columns=["SKU", "Description", "Unit Price", "Quantity", "Price", "Vat", "Amount"])
    df = pd.concat([df, total_row], ignore_index=True)

    # Generate invoice number based on base and date
    base_invoice_number = 10000
    base_date = pd.to_datetime("2024-12-24")
    current_date = pd.to_datetime(invoice_date)
    increment = (current_date - base_date).days * 5
    invoice_number = base_invoice_number + increment

    # Create PDF
    pdf = FPDF(format='A3')
    pdf.add_page()
    pdf.add_font('Amiri', '', 'files/Fonts/Amiri-Regular.ttf', uni=True)
    pdf.add_font('Amiri', 'B', 'files/Fonts/Amiri-Bold.ttf', uni=True)

    pdf.set_font("Amiri", 'B', 16)
    pdf.cell(0, 10, 'TAX INVOICE (MANUAL)', 0, 1, 'C')
    pdf.ln(10)
    pdf.cell(0, 10, shop_name, 0, 1, 'C')
    pdf.ln(10)

    pdf.set_font("Amiri", '', 14)
    pdf.cell(0, 10, 'Supplier: 337337 FAKHR ALTASHYEED EST.', 0, 0, 'L')
    pdf.cell(0, 10, 'Buyer: SOU Vegetable for South', 0, 1, 'R')
    pdf.cell(0, 10, f'Po No: {po_number}', 0, 0, 'L')
    pdf.cell(0, 10, f'Invoice No: {invoice_number}', 0, 1, 'R')
    pdf.cell(0, 10, f'Po Date: {po_date}', 0, 0, 'L')
    pdf.cell(0, 10, f'Invoice Date: {invoice_date}', 0, 1, 'R')
    pdf.ln(10)

    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Amiri", 'B', 14)
    columns = ["SKU", "Description", "Arabic Desc.", "Unit Price", "Quantity", "Price", "Vat", "Amount"]
    widths = [25, 45, 45, 25, 25, 30, 25, 30]
    for col, w in zip(columns, widths):
        pdf.cell(w, 10, col, 1, 0, 'C', fill=True)
    pdf.ln()

    pdf.set_font("Amiri", '', 14)
    for _, row in df.iterrows():
        sku = str(row["SKU"])
        eng = description_mapping.get(sku, str(row["Description"]))
        arb = arabic_description_mapping.get(sku, "")
        eng_disp = get_display(arabic_reshaper.reshape(eng))
        arb_disp = get_display(arabic_reshaper.reshape(arb))
        values = [sku, eng_disp, arb_disp,
                  f"{row['Unit Price']:.2f}" if pd.notna(row["Unit Price"]) else "",
                  str(row["Quantity"]),
                  f"{row['Price']:.2f}" if pd.notna(row["Price"]) else "",
                  f"{row['Vat']:.2f}" if pd.notna(row["Vat"]) else "",
                  f"{row['Amount']:.2f}" if pd.notna(row["Amount"]) else ""]
        for val, w in zip(values, widths):
            pdf.cell(w, 8, val, 1)
        pdf.ln()

    pdf.set_font("Amiri", 'B', 16)
    pdf.cell(0, 10, f"Total quantity: {int(df.iloc[-1]['Quantity'])}", 0, 1, 'R')
    pdf.cell(0, 10, f"Total (ex. VAT): {df.iloc[-1]['Price']:.2f} SAR", 0, 1, 'R')
    pdf.cell(0, 10, f"VAT (15%): {df.iloc[-1]['Vat']:.2f} SAR", 0, 1, 'R')
    pdf.cell(0, 10, f"Total (inc. VAT): {df.iloc[-1]['Amount']:.2f} SAR", 0, 1, 'R')
    pdf.ln(5)

    # QR Code (ZATCA-style)
    seller_name = "337337 FAKHR ALTASHYEED EST."
    tax_number = "301308065300003"
    total_amount = round(df.iloc[-1]["Amount"], 2)
    vat_amount = round(df.iloc[-1]["Vat"], 2)

    tlv = ""
    for idx, val in enumerate([
        seller_name, tax_number, invoice_date,
        f"{total_amount:.2f}", f"{vat_amount:.2f}"
    ], start=1):
        tlv += f"{idx:02x}{len(val.encode('utf-8')):02x}{val.encode().hex()}"

    b64 = codecs.encode(codecs.decode(tlv, 'hex'), 'base64').decode().replace('\n', '')
    qr = qrcode.QRCode(version=1, box_size=3, border=0.1)
    qr.add_data(b64)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    img_path = f"manual_qr_{po_number}.png"
    img.save(img_path)

    pdf.image(img_path, x=120)
    if os.path.exists(img_path):
        os.remove(img_path)

    os.makedirs(output_path, exist_ok=True)
    
    file_name = f"{shop_name.replace(' ', '_')}.pdf"
    print(f"✅ Manual invoice created: {os.path.join(output_path, file_name)}")
    pdf.output(os.path.join(output_path, file_name))