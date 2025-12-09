import csv
import os

csv_file_path = 'dataset.csv'
sql_file_path = 'u979757278_smartani.sql'

def escape_sql_string(value):
    if value is None:
        return "NULL"
    # Escape single quotes by doubling them
    return "'" + str(value).replace("'", "''").replace("\\", "\\\\") + "'"

try:
    # Read CSV
    rows = []
    with open(csv_file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"Read {len(rows)} rows from CSV.")

    # Generate SQL
    sql_statements = []
    sql_statements.append("\n\n--")
    sql_statements.append("-- Table structure for table `chatbot_dataset`")
    sql_statements.append("--")
    sql_statements.append("CREATE TABLE IF NOT EXISTS `chatbot_dataset` (")
    sql_statements.append("  `id` int(11) NOT NULL AUTO_INCREMENT,")
    sql_statements.append("  `judul` text COLLATE utf8mb4_unicode_ci,")
    sql_statements.append("  `link` text COLLATE utf8mb4_unicode_ci,")
    sql_statements.append("  `tanggal` varchar(255) COLLATE utf8mb4_unicode_ci,")
    sql_statements.append("  `ringkasan` text COLLATE utf8mb4_unicode_ci,")
    sql_statements.append("  `url_gambar_thumbnail` text COLLATE utf8mb4_unicode_ci,")
    sql_statements.append("  `isi_artikel` longtext COLLATE utf8mb4_unicode_ci,")
    sql_statements.append("  PRIMARY KEY (`id`)")
    sql_statements.append(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;")
    sql_statements.append("\n")
    
    sql_statements.append("--")
    sql_statements.append("-- Dumping data for table `chatbot_dataset`")
    sql_statements.append("--")

    if rows:
        # Construct INSERT statements
        # We'll do bulk inserts for better performance if needed, but row-by-row is safer for now to avoid huge lines
        # Actually, let's do batches of 50 to keep it clean
        
        batch_size = 50
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values_list = []
            for row in batch:
                judul = escape_sql_string(row.get('Judul', ''))
                link = escape_sql_string(row.get('Link', ''))
                tanggal = escape_sql_string(row.get('Tanggal', ''))
                ringkasan = escape_sql_string(row.get('Ringkasan', ''))
                url_gambar = escape_sql_string(row.get('URL gambar thumbnail', ''))
                isi = escape_sql_string(row.get('Isi artikel', ''))
                
                values_list.append(f"({judul}, {link}, {tanggal}, {ringkasan}, {url_gambar}, {isi})")
            
            insert_stmt = f"INSERT INTO `chatbot_dataset` (`judul`, `link`, `tanggal`, `ringkasan`, `url_gambar_thumbnail`, `isi_artikel`) VALUES\n{',\n'.join(values_list)};"
            sql_statements.append(insert_stmt)

    # Append to SQL file
    with open(sql_file_path, 'a', encoding='utf-8') as f:
        f.write('\n'.join(sql_statements))
        f.write('\n')

    print("Successfully appended SQL statements to file.")

except Exception as e:
    print(f"Error: {e}")
