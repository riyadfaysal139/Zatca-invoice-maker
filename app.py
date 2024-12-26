from flask import Flask, render_template, jsonify
from pdfInvoice import main_function

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run', methods=['POST'])
def run_main_function():
    try:
        main_function()
        return jsonify({"status": "success", "message": "Invoices created successfully!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(debug=True)
