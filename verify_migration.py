import re

sql_file_path = r'd:\Downloads\kbai\u979757278_smartani.sql'

try:
    with open(sql_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Check for CREATE TABLE
    if "CREATE TABLE IF NOT EXISTS `chatbot_dataset`" in content:
        print("PASS: Table `chatbot_dataset` creation statement found.")
    else:
        print("FAIL: Table `chatbot_dataset` creation statement NOT found.")

    # Check for INSERT statements
    insert_matches = re.findall(r"INSERT INTO `chatbot_dataset`", content)
    print(f"INFO: Found {len(insert_matches)} INSERT blocks for `chatbot_dataset`.")
    
    # Check for a specific title from the CSV to ensure data is there
    test_title = "Petani Adalah Guru"
    if test_title in content:
         print(f"PASS: Found test data '{test_title}' in SQL file.")
    else:
         print(f"FAIL: Test data '{test_title}' NOT found in SQL file.")

except Exception as e:
    print(f"Error: {e}")
