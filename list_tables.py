import re

sql_file = r'd:\Downloads\kbai\u979757278_smartani.sql'

try:
    with open(sql_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    tables = re.findall(r'CREATE TABLE `(\w+)`', content)
    print("Tables found:", tables)
except Exception as e:
    print(f"Error: {e}")
