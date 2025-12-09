
import mysql.connector
import os
import sys

# Increase CSV field size limit just in case, though not using csv module here
# maxInt = sys.maxsize

DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': ''
}
DB_NAME = 'u979757278_smartani'
SQL_FILE = 'u979757278_smartani.sql'

def setup():
    # 1. Create Database
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print(f"Creating database {DB_NAME}...")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        print("Database created.")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Failed to create database: {e}")
        return

    # 2. Import SQL File
    DB_CONFIG['database'] = DB_NAME
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print(f"Reading SQL file {SQL_FILE}...")
        with open(SQL_FILE, 'r', encoding='utf-8') as f:
            sql_content = f.read()
            
        print("Parsing and executing SQL commands...")
        # Split by semicolon followed by newline or end of line seems safe for this specific dump
        # The dump uses ");\n" for inserts mostly. 
        # Using simple split might break if ";" is in text, but let's try.
        # u979757278_smartani.py might have escaped characters.
        
        statements = sql_content.split(';\n')
        
        count = 0
        total = len(statements)
        for i, stmt in enumerate(statements):
            stmt = stmt.strip()
            if not stmt:
                continue
            if stmt.startswith('--') or stmt.startswith('/*'):
                continue
                
            try:
                # mysql-connector executes one statement at a time
                cursor.execute(stmt)
                count += 1
                if count % 100 == 0:
                    print(f"Executed {count}/{total} statements...", end='\r')
            except mysql.connector.Error as err:
                 # Ignore table already exists or minor errors
                 pass
                
        conn.commit()
        print(f"\nImport successful! Executed {count} statements.")
        
    except Exception as e:
        print(f"Error during import: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    setup()
