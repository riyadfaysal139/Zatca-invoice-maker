from playwright.sync_api import sync_playwright
import os
import requests
import pdfplumber
from datetime import datetime
import platform
import subprocess
import time
import sqlite3
import socket

class PODownloader:
    @staticmethod
    def login():
        url = 'https://selanow.com/BDS/'
        username = '337337'
        password = '12345678'
        db_path = 'Files/DB/downloaded_files.db'

        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS downloaded_files (file_name TEXT PRIMARY KEY, po_release_date TEXT)''')
        conn.commit()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=50)  # Back to visible UI and slow mode
            page = browser.new_page()
            page.goto(url)

            try:
                page.click('input[class=search]')
                page.click("div[data-value='DANUBE']")

                page.click('//*[@id="signinform"]/div[2]/div/i')
                time.sleep(1)
                page.click('//*[@id="signinform"]/div[2]/div/input[1]')

                page.click("div[data-value='JED']")

                page.fill('input[name=inputName]', username)
                page.fill('input[name=inputPassword]', password)
                page.click('button[type=submit]')

                page.get_by_text("PURCHASE ORDERS").click()
                page.get_by_text("NEW").click()
                time.sleep(2)

                new_tab_links = [
                    link.get_attribute("href")
                    for link in page.query_selector_all("a.updateViewStatus.ui.animated.fade.blue.circular.button")
                ]

                page.get_by_text("VIEWED").click()
                time.sleep(2)

                viewed_links = [
                    link.get_attribute("href")
                    for link in page.query_selector_all("a.ui.animated.fade.olive.circular.button")
                ]

                pdf_links = new_tab_links + viewed_links

                for link in pdf_links[:20]:
                    file_name = os.path.basename(link)
                    logged_po_date = PODownloader.get_logged_date(file_name, cursor)

                    if logged_po_date:
                        expected_path = os.path.join('Files', 'PO', logged_po_date, file_name)
                        if os.path.exists(expected_path):
                            print(f"{file_name} exists in DB and filesystem. Skipping.")
                            continue
                        else:
                            print(f"{file_name} exists in DB but missing on disk. Re-downloading...")

                    try:
                        print(f"Downloading: {link}")
                        response = requests.get(link)
                        response.raise_for_status()

                        with open(file_name, 'wb') as f:
                            f.write(response.content)

                        with pdfplumber.open(file_name) as pdf:
                            text = "".join(page.extract_text() for page in pdf.pages)
                            po_release_date = datetime.strptime(text.split('PO Released Date:')[1].split()[0], '%d/%m/%y').strftime('%Y-%m-%d')

                        po_date_directory = os.path.join('Files', 'PO', po_release_date)
                        os.makedirs(po_date_directory, exist_ok=True)
                        final_path = os.path.join(po_date_directory, file_name)

                        os.rename(file_name, final_path)
                        print(f"Saved: {final_path}")
                        PODownloader.log_downloaded_file(file_name, po_release_date, cursor, conn)

                        PODownloader.print_file(os.path.abspath(final_path))

                    except Exception as e:
                        print(f"Failed to download {link}: {e}")

            except Exception as e:
                print(f"Browser interaction failed: {e}")

            browser.close()
            conn.close()
        print("PODownloader... Completed")

    @staticmethod
    def get_logged_date(file_name, cursor):
        cursor.execute("SELECT po_release_date FROM downloaded_files WHERE file_name = ?", (file_name,))
        result = cursor.fetchone()
        return result[0] if result else None

    @staticmethod
    def log_downloaded_file(file_name, po_release_date, cursor, conn):
        cursor.execute("INSERT OR IGNORE INTO downloaded_files (file_name, po_release_date) VALUES (?, ?)", (file_name, po_release_date))
        conn.commit()

    @staticmethod
    def print_file(file_path):
        machine_name = socket.gethostname()
        try:
            if platform.system() == 'Windows':
                print(f"Printing '{os.path.basename(file_path)}' silently on {machine_name} (Windows default printer)...")
                os.startfile(file_path, 'print')
                print(f"✅ Successfully sent to printer: {file_path}")
            elif platform.system() == 'Darwin':
                print(f"Printing '{os.path.basename(file_path)}' silently on {machine_name} (macOS lp)...")
                subprocess.run(['lp', file_path], check=True)
                print(f"✅ Successfully sent to printer: {file_path}")
            else:
                print("⚠️ Printing is not supported on this OS.")
        except Exception as e:
            print(f"❌ Failed to print {file_path} on {machine_name}: {e}")

if __name__ == '__main__':
    PODownloader.login()
