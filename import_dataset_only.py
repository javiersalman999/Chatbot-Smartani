
import mysql.connector

DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': '',
    'database': 'u979757278_smartani'
}
SQL_FILE = 'u979757278_smartani.sql'

def import_dataset():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print(f"Reading SQL file {SQL_FILE}...")
        with open(SQL_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Find start of chatbot_dataset
        start_marker = "CREATE TABLE IF NOT EXISTS `chatbot_dataset`"
        idx = content.find(start_marker)
        
        if idx == -1:
            # Try without backticks if not found
            start_marker = "CREATE TABLE IF NOT EXISTS chatbot_dataset"
            idx = content.find(start_marker)
            
        if idx == -1:
            print("Could not find chatbot_dataset table definition in file.")
            return

        print("Found chatbot_dataset definition. Importing...")
        # Get everything from the start marker
        dataset_sql = content[idx:]
        
        # Split by semicolon
        statements = dataset_sql.split(';')
        
        count = 0
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt: continue
            
            try:
                cursor.execute(stmt)
                count += 1
                if count % 10 == 0:
                    print(f"Executed {count} statements...", end='\r')
            except mysql.connector.Error as err:
                 print(f"\n[WARN] {err}")
                 
        conn.commit()
        print(f"\nSuccess! Executed {count} statements.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    import_dataset()
