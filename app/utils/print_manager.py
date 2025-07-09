import os
import platform
import subprocess
import sqlite3
from datetime import datetime

class PrintManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS print_logs (
                filename TEXT PRIMARY KEY,
                last_printed_at TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def should_print(self, filename, filepath):
        if not os.path.exists(filepath):
            return False

        file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT last_printed_at FROM print_logs WHERE filename = ?", (filename,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return True

        last_printed = datetime.fromisoformat(row[0])
        return file_mtime > last_printed

    def update_print_log(self, filename):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("REPLACE INTO print_logs (filename, last_printed_at) VALUES (?, ?)", (filename, now))
        conn.commit()
        conn.close()

    def print_file(self, filepath):
        filename = os.path.basename(filepath)
        try:
            if platform.system() == 'Windows':
                os.startfile(filepath, 'print')
            elif platform.system() == 'Darwin':
                subprocess.run(['lp', filepath], check=True)
            else:
                print("⚠️ Unsupported platform for printing.")
                return False
            print(f"✅ Printed: {filename}")
            return True
        except Exception as e:
            print(f"❌ Failed to print {filename}: {e}")
            return False

    def print_folder(self, folder_path):
        for filename in os.listdir(folder_path):
            if filename.lower().endswith('.pdf'):
                full_path = os.path.join(folder_path, filename)
                if self.should_print(filename, full_path):
                    if self.print_file(full_path):
                        self.update_print_log(filename)
                else:
                    print(f"⏩ Skipped (already printed): {filename}")
