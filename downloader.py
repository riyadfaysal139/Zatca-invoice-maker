import requests

# Define the URL and the target file path
url = "https://www.bindawoodapps.com/DANPO/337337_0028887970_JED_00137.pdf"
output_path = "/Volumes/Mac SD/Study/My codes/pdfInvoiceMaker oct 2024/invoice_0028887970.pdf"  # Update the path as needed

# Send a GET request to download the PDF
response = requests.get(url)

# Check if the request was successful
if response.status_code == 200:
    # Open a file in binary write mode and save the content
    with open(output_path, "wb") as file:
        file.write(response.content)
    print(f"File saved successfully at {output_path}")
else:
    print("Failed to download the file.")
