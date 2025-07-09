import os
import sqlite3
import pandas as pd
from fpdf import FPDF
from pathlib import Path
import arabic_reshaper
from bidi.algorithm import get_display

ROOT = Path(__file__).resolve().parents[2]

class DailyWorksheetPDF:
    def __init__(self, po_date):
        self.po_date = po_date
        self.db_path = (ROOT / 'files' / 'DB' / 'downloaded_files.db').as_posix()
        self.output_dir = (ROOT / 'files' / 'DailyWorksheets' / po_date).as_posix()
        os.makedirs(self.output_dir, exist_ok=True)
        self.name_mapping = self.load_name_mapping((ROOT / 'files' / 'Texts' / 'name_mapping.txt').as_posix())
        self.description_mapping = self.load_mapping((ROOT / 'files' / 'Texts' / 'description_mapping.txt').as_posix())
        # Register Amiri font
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
        mapping = {}
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if ':' in line and 'base_invoice_numbers' not in line:
                    key, value = line.strip().split(':')
                    mapping[key.strip()] = value.strip()
        return mapping

    def generate(self):
        conn = sqlite3.connect(self.db_path)
        meta_df = pd.read_sql_query("SELECT po_number, file_name FROM po_metadata WHERE po_release_date = ?", conn, params=(self.po_date,))
        if meta_df.empty:
            print(f"❌ No POs found for {self.po_date}")
            return

        # Set output path first
        output_path = os.path.join(self.output_dir, f"worksheet_{self.po_date}.pdf")
        filename = os.path.basename(output_path)

        # Initialize PrintManager early
        try:
            from utils.print_manager import PrintManager
            pm = PrintManager(self.db_path)
        except Exception as e:
            print(f"⚠️ PrintManager import failed: {e}")
            pm = None

        # If file exists and PrintManager says "no need to print", skip everything
        if os.path.exists(output_path) and pm and not pm.should_print(filename, output_path):
            print(f"⏩ Worksheet already printed and unchanged: {filename}")
            return

        # Proceed with generation
        shop_po_map = {}
        sku_data = {}

        for _, row in meta_df.iterrows():
            po = row['po_number']
            loc_code = row['file_name'].split('_')[-1].replace('.pdf', '')
            shop = self.name_mapping.get(loc_code, loc_code)
            shop_po_map.setdefault(shop, []).append(po)

            df = pd.read_sql_query(f"SELECT SKU, Description, Quantity FROM po_{po}", conn).iloc[:-1]
            for _, r in df.iterrows():
                key = (r['SKU'], r['Description'])
                sku_data.setdefault(key, {}).setdefault(shop, []).append(int(r['Quantity']))

        conn.close()

        pdf = FPDF(orientation='P', unit='mm', format=(420, 297))
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 12, f"Daily Worksheet - Date: {self.po_date}", ln=True, align='C')
        pdf.ln(4)
        pdf.set_font("Arial", 'B', 12)

        shops = list(shop_po_map.keys())
        usable_width = pdf.w - pdf.l_margin - pdf.r_margin
        dynamic_width = usable_width - 30 - 60 - 30
        shop_col_width = dynamic_width / len(shops) if shops else 40
        col_widths = [30, 60] + [shop_col_width] * len(shops) + [30]

        # Header
        pdf.set_fill_color(220, 220, 220)
        pdf.cell(col_widths[0], 10, "SKU", 1, 0, 'C', fill=True)
        pdf.cell(col_widths[1], 10, "Description", 1, 0, 'C', fill=True)
        for i, shop in enumerate(shops):
            pdf.cell(col_widths[2+i], 10, shop, 1, 0, 'C', fill=True)
        pdf.cell(col_widths[-1], 10, "TOTAL", 1, 1, 'C', fill=True)

        pdf.set_font("Arial", '', 10)
        pdf.cell(col_widths[0], 8, "", 1)
        pdf.cell(col_widths[1], 8, "", 1)
        for i, shop in enumerate(shops):
            po_list = shop_po_map[shop]
            y = pdf.get_y()
            x = pdf.get_x()
            pdf.multi_cell(col_widths[2+i], 8, " & ".join(po_list), border=1, align='C')
            pdf.set_xy(x + col_widths[2+i], y)
        pdf.cell(col_widths[-1], 8, "", 1, 1)

        # Body
        available_height = pdf.h - pdf.t_margin - pdf.b_margin - pdf.get_y()
        num_rows = len(sku_data)
        row_height = available_height / num_rows if num_rows else 10

        for (sku, desc), shop_data in sorted(sku_data.items(), key=lambda x: int(x[0][0])):
            pdf.cell(col_widths[0], row_height, str(sku), 1)
            mapped_desc = self.description_mapping.get(str(sku), str(desc))
            pdf.cell(col_widths[1], row_height, mapped_desc, 1)
            total = 0
            for shop in shops:
                qtys = shop_data.get(shop, [])
                if len(qtys) == 0:
                    text = ""
                elif len(qtys) == 1:
                    text = str(qtys[0])
                else:
                    text = "+".join(map(str, qtys)) + f"={sum(qtys)}"
                pdf.cell(col_widths[2+shops.index(shop)], row_height, text, 1, 0, 'C')
                total += sum(qtys)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(col_widths[-1], row_height, str(total), 1, 1, 'C')
            pdf.set_font("Arial", '', 12)

        pdf.output(output_path)
        print(f"✅ Worksheet saved: {output_path}")

        if pm and pm.should_print(filename, output_path):
            if pm.print_file(output_path):
                pm.update_print_log(filename)

