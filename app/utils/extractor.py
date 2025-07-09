# utils/extractor.py
import os
import re
import pdfplumber
import pandas as pd
import sqlite3
from datetime import datetime

class PDFExtractor:
    def __init__(self, po_folder):
        self.po_folder = po_folder
        self.dataframes = {}
        self.extracted_files = []

    def extract(self):
        if not os.path.exists(self.po_folder):
            print(f"❌ PO folder not found: {self.po_folder}")
            return

        for filename in os.listdir(self.po_folder):
            if filename.endswith(".pdf") and not filename.startswith("._"):
                try:
                    self.process_pdf_file(filename)
                except Exception as e:
                    print(f"❌ Error processing {filename}: {e}")

    def process_pdf_file(self, filename):
        file_path = os.path.join(self.po_folder, filename)

        if not self.is_valid_pdf(file_path):
            print(f"⛔ Skipping invalid PDF: {filename}")
            return

        print(f"📄 Processing: {filename}")

        try:
            df = self.extract_table(file_path)
            df = self.clean_dataframe(df)
            df = self.calculate_totals(df)
        except Exception as e:
            print(f"⚠️ Table extraction failed for {filename}: {e}")
            return

        try:
            text = self.extract_text(file_path)
            metadata = self.extract_metadata(text, df, filename)
        except Exception as e:
            print(f"⚠️ Metadata extraction failed for {filename}: {e}")
            return

        # ✅ Ensure date inside PDF matches folder name
        input_po_date = os.path.basename(self.po_folder)
        if metadata["po_release_date"] != input_po_date:
            print(f"⚠️ Skipping {filename} — PO date mismatch: PDF says {metadata['po_release_date']}, folder is {input_po_date}")
            return

        try:
            self.save_to_db(metadata, df, filename)
            self.dataframes[filename] = df
            self.extracted_files.append(filename)
        except Exception as e:
            print(f"❌ Failed to save {filename} to DB: {e}")

    def is_valid_pdf(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                return f.read(4) == b'%PDF'
        except:
            return False

    def extract_text(self, file_path):
        text = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text.append(t)
        return "\n".join(text)

    def extract_table(self, file_path):
        data = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    lines = text.split('\n')
                    start = False
                    for line in lines:
                        if "Notes" in line:
                            break
                        if start and '--------' not in line:
                            data.append(line.split())
                        if line.strip().startswith("SKU"):
                            start = True
        return pd.DataFrame(data)

    def clean_dataframe(self, df):
        for i in range(len(df)):
            if len(df.iloc[i]) < 7:
                df.iloc[i] = df.iloc[i].tolist() + [None] * (7 - len(df.iloc[i]))

        if len(df.columns) > 5:
            df.iloc[:-1, 3:6] = None

        for i in range(1, len(df), 2):
            if i < len(df):
                df.iloc[i - 1, 1] = f"{df.iloc[i, 0]} {df.iloc[i, 1]}"

        df = df.drop(df.index[1::2][:-1])
        if len(df) > 1:
            df = df.drop(df.index[-2])

        if len(df.columns) > 5:
            df = df.drop(df.columns[[3, 4, 5]], axis=1)

        if len(df) > 0:
            df = df[:-1]

        df.columns = ["SKU", "Description", "Unit Price", "Quantity", "Price", "Vat", "Amount"]
        df = df[~df.apply(lambda row: row.astype(str).str.contains("Description|Continue to").any(), axis=1)]
        return df

    def calculate_totals(self, df):
        df["Unit Price"] = pd.to_numeric(df["Unit Price"], errors='coerce').round(3)
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors='coerce').fillna(0).astype(int)
        df["Price"] = (df["Unit Price"] * df["Quantity"]).round(4)
        df["Vat"] = (df["Price"] * 0.15).round(4)
        df["Amount"] = (df["Price"] + df["Vat"]).round(4)

        total_row = pd.DataFrame([["", "Total", "", df["Quantity"].sum(), df["Price"].sum(), df["Vat"].sum(), df["Amount"].sum()]], columns=df.columns)
        return pd.concat([df, total_row], ignore_index=True)

    def extract_metadata(self, text, df, filename):
        def find(pattern):
            match = re.search(pattern, text)
            return match.group(1).strip() if match else None

        def convert_date(d):
            try:
                return datetime.strptime(d, "%d/%m/%y").strftime("%Y-%m-%d")
            except:
                return d

        po_number = filename.split("_")[1]
        total_price = round(df.iloc[-1, 4], 4)
        total_vat = round(df.iloc[-1, 5], 4)

        return {
            "po_number": po_number,
            "po_release_date": convert_date(find(r"PO Released Date\s*:?\s*(\d{1,2}/\d{1,2}/\d{2})")),
            "supplier_name": find(r"(337337 [A-Z\s.]+) PO Released Date"),
            "buyer": find(r"Buyer\s*:?\s*([\w\s]+)"),
            "ship_to": find(r"Ship To\s*:?\s*([\w\s\-]+) Dept"),
            "supplier_vat": find(r"VAT No\.?\s*:?\s*(\d{15})"),
            "shop_vat": find(r"BDG VAT No\.?\s*:?\s*(\d{15})"),
            "expected_receiving_date": convert_date(find(r"Expected Receiving Date\s*:?\s*(\d{2}/\d{2}/\d{2})")),
            "cancellation_date": convert_date(find(r"Cancellation Date\s*:?\s*(\d{1,2}/\d{1,2}/\d{2})")),
            "total_quantity": int(df.iloc[-1, 3]) if not pd.isna(df.iloc[-1, 3]) else None,
            "total_amount": float(df.iloc[-1, 6]) if not pd.isna(df.iloc[-1, 6]) else None,
            "total_price": total_price,
            "total_vat": total_vat,
        }

    def save_to_db(self, metadata, df, filename):
        db_path = "files/DB/downloaded_files.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

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

        cursor.execute('''
            INSERT OR REPLACE INTO po_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            metadata["po_number"],
            metadata["po_release_date"],
            metadata["supplier_name"],
            metadata["buyer"],
            metadata["ship_to"],
            metadata["supplier_vat"],
            metadata["shop_vat"],
            metadata["expected_receiving_date"],
            metadata["cancellation_date"],
            metadata["total_quantity"],
            metadata["total_price"],
            metadata["total_vat"],
            metadata["total_amount"],
            filename
        ))

        table_name = f"po_{metadata['po_number']}"
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
        for _, row in df.iloc[:-1].iterrows():
            cursor.execute(f'''
                INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', tuple(row))

        conn.commit()
        conn.close()


    def print_summary(self):
        print(f"\n✅ Extracted {len(self.extracted_files)} PDF(s):")
        for file in self.extracted_files:
            print(f"   - {file}")
