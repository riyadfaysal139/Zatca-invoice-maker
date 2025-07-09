# utils/pdf_creator.py
import os
import sqlite3
import pandas as pd
from fpdf import FPDF
import qrcode
import codecs
from pathlib import Path
import arabic_reshaper
from bidi.algorithm import get_display
from datetime import datetime

class PDFCreator:
    def __init__(self, session, db_path='files/DB/downloaded_files.db', output_dir='files/Invoices'):
        self.db_path = db_path
        self.output_dir = output_dir
        self.invoice_date = session.invoice_date
        self.po_day = session.po_day
        self.invoice_day = session.invoice_day
        self.po_date = session.po_date
        os.makedirs(self.output_dir, exist_ok=True)
        self.name_mapping, self.base_invoice_numbers = self.load_name_mapping('files/Texts/name_mapping.txt')
        self.description_mapping = self.load_mapping('files/Texts/description_mapping.txt')
        self.arabic_description_mapping = self.load_mapping('files/Texts/arabic_description_mapping.txt')

        self.pdf = FPDF(orientation='P', unit='mm', format=(420, 297))  # A3 landscape page
        self.pdf.add_font("Amiri", '', 'files/Fonts/Amiri-Regular.ttf', uni=True)
        self.pdf.add_font("Amiri", 'B', 'files/Fonts/Amiri-Bold.ttf', uni=True)

    def load_mapping(self, file_path):
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

    def load_name_mapping(self, file_path):
        name_map = {}
        base_invoice_numbers = {}
        reading_base = False
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line == 'base_invoice_numbers:':
                    reading_base = True
                    continue
                key, value = line.split(':')
                if reading_base:
                    base_invoice_numbers[key.strip()] = int(value.strip())
                else:
                    name_map[key.strip()] = value.strip()
        return name_map, base_invoice_numbers

    def save_invoice_details(self, conn, invoice_number, file_name, location_code, location_name, total_qty, total_price, total_vat, total_amt, po_numbers):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.cursor()

        cursor.execute("""
        INSERT OR REPLACE INTO invoice_metadata (
            invoice_number, invoice_date, po_date, location_code, location_name,
            total_quantity, total_price, total_vat, total_amount, file_name,
            status, version, is_locked, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'final', 1, 1, ?, ?)
        """, (
            invoice_number, self.invoice_date, self.po_date, location_code, location_name,
            total_qty, total_price, total_vat, total_amt, file_name,
            now, now
        ))

        for po in po_numbers:
            cursor.execute("""
            INSERT OR IGNORE INTO invoice_po_link (invoice_number, po_number)
            VALUES (?, ?)
            """, (invoice_number, po))

        table_name = f"invoice_items_{invoice_number.replace('-', '_')}_v1"
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        cursor.execute(f"""
            CREATE TABLE {table_name} (
                SKU TEXT,
                Description TEXT,
                [Unit Price] REAL,
                Quantity INTEGER,
                Price REAL,
                Vat REAL,
                Amount REAL
            )
        """)

        return table_name

    def generate_all(self):
        self.generate_mode(merge_by_shop=True)
        self.generate_mode(merge_by_shop=False)

    def generate_mode(self, merge_by_shop):
        conn = sqlite3.connect(self.db_path)
        meta_df = pd.read_sql_query("SELECT * FROM po_metadata WHERE po_release_date = ?", conn, params=(self.po_date,))
        if meta_df.empty:
            print(f"⚠️ No POs found for selected date: {self.po_date}")
            return

        invoice_counters = {}
        grouped = meta_df.groupby(meta_df['file_name'].str.extract(r'_(\d+)\.pdf')[0]) if merge_by_shop else meta_df.groupby('po_number')

        for key, group in grouped:
            if merge_by_shop:
                po_numbers = group['po_number'].tolist()
                if len(po_numbers) == 1:
                    continue
                location_code = key
                location_name = self.name_mapping.get(location_code, location_code)
                dfs = [pd.read_sql_query(f"SELECT * FROM po_{po}", conn) for po in po_numbers]
                merged_df = pd.concat(dfs)
                df = merged_df.groupby(['SKU', 'Description'], as_index=False).agg({
                    'Unit Price': 'first',
                    'Quantity': 'sum',
                    'Price': 'sum',
                    'Vat': 'sum',
                    'Amount': 'sum'
                })
                meta_row = group.iloc[0]
                total_qty = df['Quantity'].sum()
                total_amt = df['Amount'].sum()
                total_price = round(total_amt / 1.15, 4)
                total_vat = round(total_amt - total_price, 4)
                display_po = "Merged POs: " + ", ".join(po_numbers)
            else:
                po = key
                group = group.iloc[0]
                po_numbers = [po]
                location_code = group['file_name'].split('_')[-1].replace('.pdf', '')
                location_name = self.name_mapping.get(location_code, location_code)
                df = pd.read_sql_query(f"SELECT * FROM po_{po}", conn)
                total_qty = group['total_quantity']
                total_amt = group['total_amount']
                total_price = round(total_amt / 1.15, 4)
                total_vat = round(total_amt - total_price, 4)
                display_po = f"PO No: {po}"
                meta_row = group

            base_number = self.base_invoice_numbers.get(location_name, 10000)
            base_date = pd.to_datetime("2024-12-24")
            current_date = pd.to_datetime(self.invoice_date)
            increment = (current_date - base_date).days * 5
            base_invoice = base_number + increment

            if merge_by_shop:
                invoice_number = f"{base_invoice}"
            else:
                location_po_count = len(meta_df[meta_df['file_name'].str.contains(location_code)])
                count = invoice_counters.get(location_name, 0) + 1
                invoice_counters[location_name] = count
                invoice_number = f"{base_invoice}" if location_po_count == 1 else f"{base_invoice}-{count}"

            pdf = FPDF(format='A3')
            pdf.add_page()
            self.setup_fonts(pdf)
            self.add_invoice_header(pdf, location_name, display_po, invoice_number)
            self.add_dataframe_data(pdf, df)
            self.add_summary_lines(pdf, total_qty, total_price, total_vat, total_amt)
            self.add_qr_code(pdf, po_numbers[0], self.invoice_date, total_amt)

            folder = os.path.join(self.output_dir, self.invoice_date)
            os.makedirs(folder, exist_ok=True)
            po_joined = "_".join(po_numbers)
            filename = f"{invoice_number}_{location_name}_{po_joined}.pdf"
            filepath = os.path.join(folder, filename)
            pdf.output(filepath)

            table_name = self.save_invoice_details(conn, invoice_number, filename, location_code, location_name,
                                                  total_qty, total_price, total_vat, total_amt, po_numbers)
            df.to_sql(table_name, conn, if_exists='replace', index=False)
            print(f"✅ Invoice generated and saved: {filename}")

        conn.commit()
        conn.close()

    def setup_fonts(self, pdf):
        pdf.add_font('Amiri', '', 'files/Fonts/Amiri-Regular.ttf', uni=True)
        pdf.add_font('Amiri', 'B', 'files/Fonts/Amiri-Bold.ttf', uni=True)

    def add_invoice_header(self, pdf, location_name, po_display, invoice_number):
        pdf.set_font("Amiri", 'B', 16)
        pdf.cell(0, 10, 'TAX INVOICE', 0, 1, 'C')
        pdf.ln(5)
        pdf.cell(0, 10, location_name, 0, 1, 'C')
        pdf.ln(5)
        self.add_supplier_buyer_info(pdf)
        pdf.set_font("Amiri", '', 14)
        pdf.cell(0, 10, po_display, 0, 0, 'L')
        pdf.cell(0, 10, f'Invoice NO: {invoice_number}', 0, 1, 'R')
        pdf.cell(0, 10, f'Po Date: {self.po_date}({self.po_day})', 0, 0, 'L')
        pdf.cell(0, 10, f'Invoice Date: {self.invoice_date}({self.invoice_day})', 0, 1, 'R')
        pdf.ln(10)

    def add_supplier_buyer_info(self, pdf):
        pdf.set_font("Amiri", '', 14)
        pdf.cell(0, 10, 'Supplier: 337337 FAKHR ALTASHYEED EST.', 0, 0, 'L')
        pdf.cell(0, 10, 'Buyer: SOU Vegetable for South', 0, 1, 'R')
        pdf.cell(0, 10, 'Tax Reg. Number: 301308065300003', 0, 0, 'L')
        pdf.cell(0, 10, 'Tax Reg. Number: 310072568710003', 0, 1, 'R')
        pdf.cell(0, 10, 'Phone: 0501212591-0507006855', 0, 0, 'L')
        pdf.cell(0, 10, '-----------------------------', 0, 1, 'R')

    def add_dataframe_data(self, pdf, dataframe):
        num_columns = len(dataframe.columns) + 1
        col_widths = []
        for col in dataframe.columns:
            if col == 'SKU':
                col_widths.append(20)
            elif col == 'Description':
                col_widths.append(45)
                col_widths.append(45)
            elif col == 'Unit Price':
                col_widths.append(20)
            else:
                col_widths.append((280 - 145) / (len(dataframe.columns) - 3))

        pdf.set_fill_color(230, 230, 230)
        pdf.set_font("Amiri", 'B', 14)
        for i, column in enumerate(dataframe.columns):
            pdf.cell(col_widths[i], 10, column, 1, 0, 'C', fill=True)
            if column == 'Description':
                pdf.cell(col_widths[i], 10, "Arabic Desc.", 1, 0, 'C', fill=True)
        pdf.ln()
        pdf.set_font("Amiri", '', 12)

        row_height = 8
        for _, row in dataframe.iterrows():
            for i, item in enumerate(row):
                if i == 1:
                    sku = row.iloc[0]
                    desc = self.description_mapping.get(str(sku), str(item))
                    arabic_desc = self.arabic_description_mapping.get(str(sku), "")
                    bidi = get_display(arabic_reshaper.reshape(desc))
                    bidi_ar = get_display(arabic_reshaper.reshape(arabic_desc))
                    pdf.cell(col_widths[i], row_height, bidi, 1)
                    pdf.cell(col_widths[i], row_height, bidi_ar, 1)
                else:
                    pdf.cell(col_widths[i], row_height, str(item), 1)
            pdf.ln(row_height)

    def add_summary_lines(self, pdf, total_quantity, total_price, total_vat, total_amount):
        pdf.set_font("Amiri", 'B', 15)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(0, 10, f"Total quantity:   {total_quantity}", 0, 0, 'C', fill=False)
        pdf.cell(0, 10, f"Total (ex. vat): {total_price:.4f} SAR", 0, 1, 'R', fill=False)
        pdf.cell(0, 10, "", 0, 0, 'C', fill=True)
        pdf.cell(0, 10, f"Total vat (15%): {total_vat:.4f} SAR", 0, 1, 'R', fill=False)
        pdf.cell(0, 10, "", 0, 0, 'C', fill=False)
        pdf.cell(0, 10, f"Total (inc. vat): {total_amount:.4f} SAR", 0, 1, 'R', fill=False)

    def add_qr_code(self, pdf, po_number, invoice_day, total_amount):
        seller_name = "337337 FAKHR ALTASHYEED EST."
        tax_number = "301308065300003"
        invoice_date = invoice_day.split()[0]
        total_amount = round(total_amount, 4)
        total_price = round(total_amount / 1.15, 4)
        vat_amount = round(total_amount - total_price, 4)

        tlv1 = f"01{len(seller_name):02x}{seller_name.encode().hex()}"
        tlv2 = f"02{len(tax_number):02x}{tax_number.encode().hex()}"
        tlv3 = f"03{len(invoice_date):02x}{invoice_date.encode().hex()}"
        tlv4 = f"04{len(str(total_amount)):02x}{str(total_amount).encode().hex()}"
        tlv5 = f"05{len(str(vat_amount)):02x}{str(vat_amount).encode().hex()}"

        tlv = f"{tlv1}{tlv2}{tlv3}{tlv4}{tlv5}"
        b64 = codecs.encode(codecs.decode(tlv, 'hex'), 'base64').decode().replace('', '')

        qr = qrcode.QRCode(version=1, box_size=3, border=0.1)
        qr.add_data(b64)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        img_path = f"qr_{po_number}.png"
        img.save(img_path)

        pdf.image(img_path, x=120)

        if os.path.exists(img_path):
            os.remove(img_path)
