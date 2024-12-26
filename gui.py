import tkinter as tk
from tkinter import messagebox
from pdfInvoice import main_function  # Ensure this matches the function definition

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Invoice Maker")
        self.geometry("400x200")

        self.label = tk.Label(self, text="PDF Invoice Maker", font=("Arial", 16))
        self.label.pack(pady=20)

        self.run_button = tk.Button(self, text="Run", command=self.run_main_function)
        self.run_button.pack(pady=10)

    def run_main_function(self):
        try:
            main_function()  # Call the main function from pdfInvoice.py
            messagebox.showinfo("Success", "Invoices created successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

if __name__ == "__main__":
    app = Application()
    app.mainloop()
