from datetime import datetime, timedelta
import pytz

ksa_timezone = pytz.timezone('Asia/Riyadh')

def get_date(days=0, specific_date=None):
    if specific_date:
        date = datetime.strptime(specific_date, "%Y-%m-%d")
    else:
        date = datetime.now(ksa_timezone)
    return (date + timedelta(days=days)).strftime("%Y-%m-%d")

def get_day(date):
    if isinstance(date, str):
        date = datetime.strptime(date, "%Y-%m-%d")
    return date.strftime("%A")
