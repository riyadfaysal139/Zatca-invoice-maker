from utils.date_utils import get_date, get_day

class POInvoiceSession:
    def __init__(self, po_date: str = None):
        self.po_date = po_date or get_date()
        self.invoice_date = get_date(1, self.po_date)
        self.po_day = get_day(self.po_date)
        self.invoice_day = get_day(self.invoice_date)

    def __str__(self):
        return (
            f"POInvoiceSession(\n"
            f"  PO Date: {self.po_date} ({self.po_day})\n"
            f"  Invoice Date: {self.invoice_date} ({self.invoice_day})\n"
            f")"
        )
    
    

if __name__ == "__main__":
    session = POInvoiceSession("2025-07-07")
    print(session)
