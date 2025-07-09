# app/orchestrator.py
from utils.session import POInvoiceSession
from utils.extractor import PDFExtractor
from utils.pdf_creator import PDFCreator  # ✅ Add this import
from pathlib import Path
from utils.ubl_generator import create_ubl_xml_from_db
from utils.poDownloader import PODownloader
from utils.print_manager import PrintManager
from utils.dailyworksheet import DailyWorksheetPDF
import os

def run_pipeline(po_date: str = None):
    session = POInvoiceSession(po_date)
    print("🎯 Starting pipeline...")
    print(session)

    # ✅ Download POs using the session date
    PODownloader.login()
    po_path = Path("files/PO") / po_date
    extractor = PDFExtractor(po_folder=po_path)
    extractor.extract()
    extractor.print_summary()

    # ✅ Generate invoices using the same session (uses invoice_date)
    creator = PDFCreator(session)
    creator.generate_all()

    worksheet = DailyWorksheetPDF(session.po_date)
    worksheet.generate()

    # After invoice generation
    printer = PrintManager(db_path='files/DB/downloaded_files.db')

    invoice_folder = os.path.join('files', 'Invoices', session.invoice_date)
    printer.print_folder(invoice_folder)

    create_ubl_xml_from_db("0031585532", session=session)


    print("✅ Pipeline complete.")



