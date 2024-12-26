import chardet

def check_encoding(file_path):
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result['encoding']

file_path = 'description_mapping.txt'
encoding = check_encoding(file_path)
print(f"The encoding of the file is: {encoding}")
