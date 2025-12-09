import os
import sys
import time
import google.generativeai as genai
import pandas as pd

# ==========================================
# KONFIGURASI
# ==========================================
API_KEY = "AIzaSyCkgId9TQjFKYUmW_UfnS3SfB88K3sIh4U"
DATASET_FILE = "dataset.xlsx"

# ==========================================
# SYSTEM INSTRUCTION (STRICT & GROUNDED)
# ==========================================
SYSTEM_INSTRUCTION = """
ANDA ADALAH AGRIBOT, ASISTEN PERTANIAN YANG JUJUR DAN BERBASIS DATA.

TUGAS ANDA:
Menjawab pertanyaan user HANYA dengan informasi yang ditemukan dalam "DATASET REFERENSI".

ATURAN PENJAWABAN (WAJIB):
1.  **TO THE POINT (KESIMPULAN SAJA):** Jawab langsung ke inti pertanyaan. Jangan bertele-tele. Berikan jawaban yang padat, ringkas, dan langsung menjawab "apa/mengapa/bagaimana".
2.  **TETAP BERBASIS DATA:** Jawaban harus 100% dari dataset.
3.  **KUTIP SUMBER DI AKHIR:** Sertakan sumber referensi (Judul Artikel) di akhir jawaban dalam kurung atau sebagai catatan kaki singkat.
    *   Contoh: "Hidroponik adalah metode tanam air tanpa tanah. (Sumber: Masa Depan Tanpa Tanah)"
4.  **JANGAN MENGARANG:** Jika data tidak ada, katakan "Data tidak ditemukan."

FOKUS: BERIKAN KESIMPULAN/INTISARI DARI DATASET YANG RELEVAN.
"""

def get_best_model():
    """Mencari model terbaik yang tersedia di akun user."""
    print("[SYSTEM] Memindai model AI yang tersedia...", end='')
    valid_model = None
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        print(" Selesai.")
        
        # Prioritas model (Pro > Flash > Standard)
        priority = [
            "models/gemini-1.5-pro-latest", "models/gemini-1.5-pro",
            "models/gemini-1.5-flash-latest", "models/gemini-1.5-flash",
            "models/gemini-pro"
        ]
        
        for p in priority:
            if p in available_models:
                valid_model = p
                break
        
        if not valid_model and available_models:
            valid_model = available_models[0]
            
    except Exception as e:
        print(f"\n[ERROR] Gagal scan model: {e}")
        return None

    return valid_model

def load_dataset(filepath):
    """Membaca dataset secara REAL (tanpa simulasi palsu)."""
    if not os.path.exists(filepath):
        print(f"[ERROR] File '{filepath}' tidak ditemukan.")
        sys.exit(1)

    print(f"[SYSTEM] Membaca file '{filepath}'...")
    try:
        # Coba baca Excel
        df = pd.read_excel(filepath)
        
        # Konversi ke string terstruktur
        # Format: Judul: [Judul] \n Isi: [Isi] \n...
        dataset_text = ""
        count = 0
        for index, row in df.iterrows():
            # Gabungkan semua kolom menjadi satu blok teks
            row_text = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
            dataset_text += f"--- DATA KE-{index+1} ---\n{row_text}\n\n"
            count += 1
            
        print(f"[SYSTEM] Berhasil memuat {count} data/artikel ke dalam memori.")
        return dataset_text
        
    except Exception as e:
        print(f"[ERROR] Gagal membaca dataset: {e}")
        sys.exit(1)

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=============================================")
    print("   AGRIBOT - STRICT DATASET MODE             ")
    print("=============================================")

    # 1. Setup API
    genai.configure(api_key=API_KEY)

    # 2. Load Real Data
    dataset_content = load_dataset(DATASET_FILE)

    # 3. Select Model
    model_name = get_best_model()
    if not model_name:
        print("[FATAL] Tidak ada model Gemini yang bisa diakses. Cek API Key.")
        sys.exit(1)
    
    print(f"[SYSTEM] Menggunakan Model: {model_name}")

    # 4. Initialize Chat
    # Kita masukkan dataset langsung ke history awal agar model "mengingatnya"
    print("[SYSTEM] Menyuntikkan dataset ke otak AI...")
    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        chat = model.start_chat(history=[
            {
                "role": "user",
                "parts": [f"INI ADALAH DATASET REFERENSI ANDA:\n\n{dataset_content}\n\nPelajari data di atas. Jangan menjawab di luar data ini."]
            },
            {
                "role": "model",
                "parts": ["Dimengerti. Saya telah menyimpan dataset ini dalam memori kerja saya. Saya hanya akan menjawab pertanyaan berdasarkan fakta yang ada di dalam teks tersebut dan akan menyertakan sumber referensinya."]
            }
        ])
        
        print("\n[READY] AgriBot Siap. Silakan tanya.")
        print("(Ketik 'exit' untuk keluar)\n")

        while True:
            user_input = input("User > ").strip()
            if not user_input: continue
            if user_input.lower() in ['exit', 'keluar']:
                break

            print("AgriBot > Menganalisis dataset...", end='\r')
            try:
                response = chat.send_message(user_input)
                print(" " * 40, end='\r')
                print(f"AgriBot > {response.text}")
            except Exception as e:
                print(f"\n[ERROR] {e}")

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")

if __name__ == "__main__":
    main()
