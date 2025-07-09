# utils/ubl_generator.py

import uuid
from datetime import datetime
from lxml import etree
import sqlite3
import pandas as pd
import os
import base64


def create_ubl_xml_from_db(po_number, session=None, db_path='files/DB/downloaded_files.db', output_dir='files/UBLs'):
    os.makedirs(output_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)

    # Load metadata
    meta_query = "SELECT * FROM po_metadata WHERE po_number = ?"
    meta_df = pd.read_sql_query(meta_query, conn, params=(po_number,))
    if meta_df.empty:
        print(f"❌ PO {po_number} not found in metadata.")
        return
    meta = meta_df.iloc[0].to_dict()

    if session:
        meta['invoice_date'] = session.invoice_date

    # Load item table
    table_name = f"po_{po_number}"
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    conn.close()

    NSMAP = {
        None: "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
    }

    def cbc(tag, text):
        el = etree.Element(f"{{{NSMAP['cbc']}}}{tag}", nsmap=NSMAP)
        el.text = str(text)
        return el

    def cac(tag, children=None):
        el = etree.Element(f"{{{NSMAP['cac']}}}{tag}", nsmap=NSMAP)
        if children:
            for child in children:
                el.append(child)
        return el

    # Root
    root = etree.Element("Invoice", nsmap=NSMAP)

    # UBLExtensions (placeholder for digital signature)
    ext_el = etree.Element(f"{{{NSMAP['ext']}}}UBLExtensions", nsmap=NSMAP)
    ext_el.append(etree.Element(f"{{{NSMAP['ext']}}}UBLExtension"))
    root.append(ext_el)

    root.append(cbc("UBLVersionID", "2.1"))
    root.append(cbc("CustomizationID", "urn:zatca:invoice:standard:1.0"))
    root.append(cbc("ProfileID", "reporting:1.0"))
    root.append(cbc("ID", str(uuid.uuid4())))
    root.append(cbc("UUID", str(uuid.uuid4())))
    root.append(cbc("IssueDate", meta['invoice_date']))
    root.append(cbc("InvoiceTypeCode", "388"))

    # Supplier
    supplier = cac("AccountingSupplierParty", [
        cac("Party", [
            cbc("Name", meta['supplier_name']),
            cac("PartyIdentification", [cbc("ID", meta['supplier_vat'])])
        ])
    ])
    root.append(supplier)

    # Buyer
    buyer = cac("AccountingCustomerParty", [
        cac("Party", [
            cbc("Name", meta['buyer']),
            cac("PartyIdentification", [cbc("ID", meta['shop_vat'])])
        ])
    ])
    root.append(buyer)

    # Tax Total
    tax_total = cac("TaxTotal", [
        cbc("TaxAmount", f"{meta['total_vat']:.2f}"),
        cac("TaxSubtotal", [
            cbc("TaxableAmount", f"{meta['total_price']:.2f}"),
            cbc("TaxAmount", f"{meta['total_vat']:.2f}"),
            cac("TaxCategory", [
                cbc("ID", "S"),
                cbc("Percent", "15"),
                cac("TaxScheme", [cbc("ID", "VAT")])
            ])
        ])
    ])
    root.append(tax_total)

    # Monetary Total
    root.append(cac("LegalMonetaryTotal", [
        cbc("LineExtensionAmount", f"{meta['total_price']:.2f}"),
        cbc("TaxExclusiveAmount", f"{meta['total_price']:.2f}"),
        cbc("TaxInclusiveAmount", f"{meta['total_amount']:.2f}"),
        cbc("PayableAmount", f"{meta['total_amount']:.2f}")
    ]))

    # Invoice Lines
    for idx, row in df.iterrows():
        item = cac("Item", [cbc("Name", row['Description'])])
        price = cac("Price", [cbc("PriceAmount", f"{row['Unit Price']:.2f}")])
        tax = cac("ClassifiedTaxCategory", [cbc("ID", "S"), cbc("Percent", "15"), cac("TaxScheme", [cbc("ID", "VAT")])])
        item.append(tax)

        line = cac("InvoiceLine", [
            cbc("ID", str(idx + 1)),
            cbc("InvoicedQuantity", int(row['Quantity'])),
            cbc("LineExtensionAmount", f"{row['Price']:.2f}"),
            item,
            price
        ])
        root.append(line)

    # Output
    tree = etree.ElementTree(root)
    output_path = os.path.join(output_dir, f"invoice_{po_number}.xml")
    tree.write(output_path, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    print(f"✅ UBL XML saved: {output_path}")


if __name__ == "__main__":
    create_ubl_xml_from_db("0031585532")
