
import mysql.connector
import csv
import sys

# Increase CSV field size limit
csv.field_size_limit(sys.maxsize)

DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': '',
    'database': 'u979757278_smartani'
}

CSV_FILE = 'dataset.csv'

def seed():
    try:
        # Connect to DB
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 1. Create Table (Drop if exists to ensure clean state or just IF NOT EXISTS)
        # For this task, let's DROP to be sure we fix broken partial imports
        print("Recreating table chatbot_dataset...")
        cursor.execute("DROP TABLE IF EXISTS chatbot_dataset")
        
        create_table_sql = """
        CREATE TABLE `chatbot_dataset` (
          `id` int(11) NOT NULL AUTO_INCREMENT,
          `judul` text COLLATE utf8mb4_unicode_ci,
          `link` text COLLATE utf8mb4_unicode_ci,
          `tanggal` varchar(255) COLLATE utf8mb4_unicode_ci,
          `ringkasan` text COLLATE utf8mb4_unicode_ci,
          `url_gambar_thumbnail` text COLLATE utf8mb4_unicode_ci,
          `isi_artikel` longtext COLLATE utf8mb4_unicode_ci,
          PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        cursor.execute(create_table_sql)
        
        # 2. Read CSV and Insert
        print(f"Reading {CSV_FILE}...")
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        print(f"Inserting {len(rows)} rows...")
        
        insert_sql = """
        INSERT INTO chatbot_dataset 
        (judul, link, tanggal, ringkasan, url_gambar_thumbnail, isi_artikel) 
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        
        data_to_insert = []
        for row in rows:
            data_to_insert.append((
                row.get('Judul', ''),
                row.get('Link', ''),
                row.get('Tanggal', ''),
                row.get('Ringkasan', ''),
                row.get('URL gambar thumbnail', ''),
                row.get('Isi artikel', '')
            ))
            
        # Bulk Insert
        cursor.executemany(insert_sql, data_to_insert)
        conn.commit()
        
        print(f"Successfully inserted {cursor.rowcount} records.")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    seed()
