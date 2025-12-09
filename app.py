from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import sys
import time
import google.generativeai as genai

# ==========================================
# KONFIGURASI
# ==========================================
# API KEY ROTATION POOL
# Tambahkan key cadangan di sini. Sistem akan otomatis ganti jika limit habis.
API_KEYS = [
    "AIzaSyBoIBCKcUwd-E9yuJtlubSgRHXYoYGvV4M", # Primary Key (New)
    "AIzaSyCkgId9TQjFKYUmW_UfnS3SfB88K3sIh4U", # Backup Key (Old)
]
CURRENT_KEY_INDEX = 0

# DATASET_FILE = "dataset.xlsx" # Tidak digunakan lagi
MODEL_NAME = "gemini-2.5-flash"

# Database Configuration
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root', 
    'password': '',
    'database': 'u979757278_smartani'
}

# Initialize Flask App
app = Flask(__name__, template_folder='.', static_folder='.')
from flask_cors import CORS
CORS(app)

# ==========================================
# LAYER 1: LOCAL INTELLIGENCE (GEMINI + MySQL)
# ==========================================
SYSTEM_INSTRUCTION = """
ANDA ADALAH SCIENTIFIC AGRIBOT.
TUGAS: Jawab pertanyaan user berdasarkan DATASET yang diberikan.

ATURAN KRUSIAL (STRICT MODE):
1. Cek apakah jawaban SPESIFIK untuk kasus user ada di DATASET.
2. JIKA pertanyaan user mengandung detail spesifik (seperti ukuran tanah "200m x 100m", lokasi detail "jauh dari pantai dan gunung") DAN dataset TIDAK memuat artikel yang membahas kasus persis tersebut: Jawab "SEARCH_EXTERNAL".
3. JANGAN MENCOCOK-COCOKKAN data umum (misal: hanya ada data "padi", lalu anda menyarankan padi untuk kasus spesifik user padahal tidak ada kaitan langsung di teks). ITU DILARANG.
4. JIKA ADA data yang relevan dan LANGSUNG menjawab pertanyaan tanpa asumsi: Jawab dengan ringkas dan sertakan sumbernya.
5. JIKA TIDAK ADA: Jawab HANYA dengan satu kata: "SEARCH_EXTERNAL".
   (Jangan minta maaf, jangan basa-basi, jangan bilang "tidak tahu". Cukup "SEARCH_EXTERNAL").

Fokus: Akurasi data lokal adalah prioritas utama. Jangan memaksakan jawaban lokal jika tidak pas.
"""

# Global variables for model and chat session
model = None
chat_session = None
dataset_context = ""

def check_dependencies():
    """Memastikan library terinstall."""
    required = ['pandas', 'openpyxl', 'requests', 'google-generativeai', 'flask', 'mysql-connector-python']
    missing = []
    for lib in required:
        try:
            if lib == 'mysql-connector-python':
                import mysql.connector
            else:
                __import__(lib.replace('-', '_')) # handle google-generativeai -> google_generativeai
        except ImportError:
            # Special case for google-generativeai which is imported as google.generativeai
            if lib == 'google-generativeai':
                try:
                    import google.generativeai
                except ImportError:
                    missing.append(lib)
            else:
                missing.append(lib)
    
    if missing:
        print(f"[ERROR] Library kurang: {', '.join(missing)}")
        print(f"Run: pip install {' '.join(missing)}")
        pass 

def load_from_mysql():
    """Membaca data dari database MySQL dan mengubahnya menjadi string context."""
    import mysql.connector
    
    print(f"[MYSQL] Connecting to {DB_CONFIG['host']}...")
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        # Select important columns from chatbot_dataset
        query = "SELECT judul, ringkasan, isi_artikel FROM chatbot_dataset"
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            print("[MYSQL] Warning: Table 'chatbot_dataset' is empty.")
            return ""

        # Konversi ke format teks yang mudah dibaca LLM
        text_data = ""
        for i, row in enumerate(rows):
            text_data += f"--- DATA {i+1} ---\n"
            text_data += f"JUDUL: {row['judul']}\n"
            text_data += f"RINGKASAN: {row['ringkasan']}\n"
            text_data += f"ISI: {row['isi_artikel']}\n"
            text_data += "\n"
            
        print(f"[MYSQL] Successfully loaded {len(rows)} records.")
        cursor.close()
        conn.close()
        return text_data
        
    except mysql.connector.Error as err:
        print(f"[ERROR] MySQL Error: {err}")
        print("Pastikan XAMPP/MySQL berjalan dan database 'u979757278_smartani' sudah dibuat.")
        return ""
    except Exception as e:
        print(f"[ERROR] Gagal baca database: {e}")
        return ""

# ==========================================
# HELPER: RETRY MECHANISM & KEY ROTATION
# ==========================================
def rotate_key():
    """Mengganti API Key aktif ke key berikutnya dalam list."""
    global CURRENT_KEY_INDEX
    CURRENT_KEY_INDEX = (CURRENT_KEY_INDEX + 1) % len(API_KEYS)
    new_key = API_KEYS[CURRENT_KEY_INDEX]
    
    # Validasi key placeholder
    if "INPUT_API_KEY" in new_key:
        print(f"\n[ROTATION] Warning: Key indek {CURRENT_KEY_INDEX} masih placeholder. Melewati...")
        return rotate_key() # Rekursif cari key berikutnya yang valid
        
    print(f"\n[ROTATION] Mengganti ke API Key indek {CURRENT_KEY_INDEX}...")
    genai.configure(api_key=new_key)
    return True

def generate_with_retry(func, *args, **kwargs):
    """Wrapper untuk retry otomatis dengan rotasi key jika kena limit."""
    max_retries = 5
    base_wait = 5 # Detik, dipercepat karena ada rotasi
    
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str or "resource exhausted" in error_str:
                print(f"\n[QUOTA] API Limit reached on key index {CURRENT_KEY_INDEX}.")
                
                # Coba rotasi key
                if len(API_KEYS) > 1:
                    try:
                        rotate_key()
                        print("[RETRY] Mencoba ulang segera dengan key baru...")
                        continue # Langsung retry tanpa sleep lama
                    except RecursionError:
                         print("[ROTATION] Semua key sepertinya habis/invalid.")
                
                # Jika hanya 1 key atau semua key habis, fallback ke sleep
                wait_time = base_wait * (2 ** attempt)
                print(f"[WAIT] Menunggu {wait_time} detik...")
                time.sleep(wait_time)
            else:
                raise e 
                
    raise Exception("Gagal: Seluruh API Key limit dan max retries terlampaui.")

# ==========================================
# LAYER 2: EXTERNAL INTELLIGENCE (SEMANTIC SCHOLAR)
# ==========================================
def synthesize_external_data(query, papers):
    """Menggunakan Gemini untuk menyimpulkan hasil pencarian eksternal."""
    try:
        # Format data untuk prompt
        context_text = ""
        for i, p in enumerate(papers):
            context_text += f"Jurnal {i+1}: {p['title']}\nAbstrak: {p.get('abstract', 'Tidak ada abstrak')}\n\n"

        prompt = f"""
        TUGAS: Jawab pertanyaan user berdasarkan ringkasan jurnal ilmiah di bawah ini.
        
        PERTANYAAN: {query}
        
        DATA JURNAL:
        {context_text}
        
        INSTRUKSI:
        1. Buat KESIMPULAN KOMPREHENSIF yang menjawab pertanyaan.
        2. Jangan menyebutkan "Berdasarkan jurnal 1...", langsung saja rangkum isinya menjadi satu narasi ilmiah.
        3. Bahasa Indonesia formal & ilmiah.
        """
        
        # Gunakan model yang sama dengan konfigurasi global
        model_synth = genai.GenerativeModel(MODEL_NAME)
        # response = model_synth.generate_content(prompt)
        response = generate_with_retry(model_synth.generate_content, prompt)
        return response.text.strip()
    except Exception as e:
        return f"[Error Synthesis] Gagal menyimpulkan data: {e}"

def optimize_search_query(user_query, session_context=None):
    """Mengubah pertanyaan user yang kompleks menjadi keyword pencarian efektif."""
    try:
        # Jika ada konteks sebelumnya, tambahkan sebagai konteks untuk follow-up
        context_hint = ""
        if session_context and session_context.get("first_question"):
            context_hint = f"""
        
        KONTEKS PERCAKAPAN SEBELUMNYA:
        - Pertanyaan awal: {session_context['first_question']}
        - Jawaban singkat: {session_context['first_answer'][:200] if session_context.get('first_answer') else 'N/A'}
        
        INSTRUKSI TAMBAHAN: Jika pertanyaan saat ini adalah follow-up dari pertanyaan awal, AUGMENT keyword dengan detail dari konteks sebelumnya (mis: jenis tanaman, ukuran lahan, lokasi, modal, dst) agar hasil pencarian tetap RELEVAN ke kasus spesifik user, bukan generic."""
        
        prompt = f"""
        TUGAS: Ekstrak keyword pencarian untuk Semantic Scholar (database jurnal ilmiah) dari pertanyaan user.
        
        PERTANYAAN USER: "{user_query}"{context_hint}
        
        ATURAN:
        1. Ambil inti topik ilmiahnya saja.
        2. Buang kata-kata sambung atau detail angka yang tidak relevan untuk PENCARIAN JUDUL JURNAL (tapi detail angka penting untuk jawaban akhir nanti).
        3. Utamakan istilah bahasa Inggris jika topiknya umum, atau Indonesia jika spesifik lokal.
        4. Output HANYA string keyword. Jangan ada penjelasan lain.
        
        CONTOH:
        Input: "Tanaman apa yang cocok untuk lahan gambut yang asam?"
        Output: peatland agriculture crops acid soil
        
        Input: "{user_query}"
        Output:
        """
        model_opt = genai.GenerativeModel(MODEL_NAME)
        # response = model_opt.generate_content(prompt)
        response = generate_with_retry(model_opt.generate_content, prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[Warning] Gagal optimasi query: {e}")
        return user_query

def search_semantic_scholar(original_query, session_context=None):
    """Mencari jurnal ilmiah jika data lokal tidak ada."""
    import requests
    import time
    
    # 1. Optimasi Query (Natural Language -> Keywords)
    search_keywords = optimize_search_query(original_query, session_context)
    print(f"\n[LAYER 2] Mencari di Semantic Scholar: '{search_keywords}'...")
    
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": search_keywords,
        "limit": 5,
        "fields": "title,authors,year,abstract,url"
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                papers = data.get('data', [])
                
                if not papers:
                    return f"[LAYER 2] Tidak ditemukan jurnal terkait untuk kata kunci: '{search_keywords}'."
                
                # --- SYNTHESIS STEP ---
                synthesis = synthesize_external_data(original_query, papers)
                
                # --- FORMAT OUTPUT ---
                result_text = f"\n=== KESIMPULAN ILMIAH (External) ===\n{synthesis}\n"
                result_text += "\n=== REFERENSI SUMBER ===\n"
                
                for i, paper in enumerate(papers):
                    title = paper.get('title', 'No Title')
                    year = paper.get('year', 'N/A')
                    url_link = paper.get('url', '-')
                    
                    # Format Authors
                    authors = paper.get('authors', [])
                    author_names = ", ".join([a['name'] for a in authors[:3]]) # Ambil 3 penulis pertama
                    if len(authors) > 3: author_names += " et al."

                    result_text += f"[{i+1}] {title} ({year}) - {author_names}\n"
                    result_text += f"    Link: {url_link}\n"
                
                return result_text
            
            elif response.status_code == 429:
                wait_time = (attempt + 1) * 2 # 2s, 4s, 6s
                time.sleep(wait_time)
                continue
                
            else:
                return f"[LAYER 2] Gagal menghubungi API (Status: {response.status_code})"
                
        except Exception as e:
            return f"[LAYER 2] Error koneksi: {e}"
            
    return "[LAYER 2] Gagal: Terlalu banyak permintaan (Rate Limit Exceeded)."

# ==========================================
# FLASK ROUTES
# ==========================================

@app.route('/')
def index():
    return send_from_directory('.', 'smartani.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# Session storage (simple in-memory for demo purposes)
# In production, use a proper session management or database
sessions = {}

@app.route('/api/chat', methods=['POST'])
def chat():
    global chat_session, dataset_context
    
    # Handle multipart/form-data or JSON
    user_input = ""
    session_id = "default"
    uploaded_file = None

    if request.content_type.startswith('multipart/form-data'):
        user_input = request.form.get('message', '')
        session_id = request.form.get('session_id', 'default')
        if 'file' in request.files:
            uploaded_file = request.files['file']
    else:
        data = request.json
        user_input = data.get('message', '')
        session_id = data.get('session_id', 'default')
    
    if not user_input and not uploaded_file:
        return jsonify({"error": "No message or file provided"}), 400

    # Initialize session if needed
    if session_id not in sessions:
        sessions[session_id] = {
            "first_question": None,
            "first_answer": None,
            "conversation_count": 0,
            "history": [
                {"role": "user", "parts": [f"DATASET LOKAL:\n{dataset_context}\n\nHafalkan data ini."]},
                {"role": "model", "parts": ["Siap. Saya sudah menghafal dataset ini."]}
            ]
        }
        # Start new chat with history
        sessions[session_id]['chat_obj'] = model.start_chat(history=sessions[session_id]['history'])

    current_session = sessions[session_id]
    chat_obj = current_session['chat_obj']

    try:
        # Prepare message parts
        message_parts = []
        if user_input:
            message_parts.append(user_input)
        
        if uploaded_file:
            # Save temp file to process
            import tempfile
            from werkzeug.utils import secure_filename
            
            filename = secure_filename(uploaded_file.filename)
            temp_path = os.path.join(tempfile.gettempdir(), filename)
            uploaded_file.save(temp_path)
            
            # Upload to Gemini
            print(f"[UPLOAD] Uploading {filename} to Gemini...")
            gemini_file = genai.upload_file(temp_path)
            message_parts.append(gemini_file)
            
            # Wait for processing if video (usually fast for images)
            # time.sleep(1) 

        # --- LAYER 1 CHECK ---
        # response = chat_obj.send_message(message_parts)
        response = generate_with_retry(chat_obj.send_message, message_parts)
        answer = response.text.strip()
        
        # Track pertanyaan pertama untuk konteks follow-up
        if current_session["conversation_count"] == 0:
            current_session["first_question"] = user_input
            current_session["first_answer"] = answer if "SEARCH_EXTERNAL" not in answer else "[Mencari di external sources...]"
        current_session["conversation_count"] += 1
        
        if "SEARCH_EXTERNAL" in answer:
            # --- LAYER 2 TRIGGER ---
            external_result = search_semantic_scholar(user_input, current_session)
            
            if "Gagal" in external_result or "Tidak ditemukan" in external_result:
                # --- LAYER 3: FALLBACK GENERAL KNOWLEDGE ---
                fallback_prompt = f"""
                PERTANYAAN: {user_input}
                
                KONDISI: Data lokal tidak ada, dan akses jurnal ilmiah gagal/kosong.
                
                TUGAS: Jawab pertanyaan ini berdasarkan pengetahuan umum agrikultur Anda sebagai AI.
                
                PERINGATAN: Awali jawaban dengan "[Disclaimer: Jawaban ini berdasarkan pengetahuan umum AI, bukan jurnal spesifik karena gangguan koneksi/data]."
                """
                # fallback_response = chat_obj.send_message(fallback_prompt)
                fallback_response = generate_with_retry(chat_obj.send_message, fallback_prompt)
                final_answer = fallback_response.text
            else:
                # Inject external synthesis into chat history
                try:
                    # chat_obj.send_message(f"[EXTERNAL_SUMMARY]\n{external_result}\nGunakan ini sebagai konteks untuk pertanyaan berikutnya.")
                    generate_with_retry(chat_obj.send_message, f"[EXTERNAL_SUMMARY]\n{external_result}\nGunakan ini sebagai konteks untuk pertanyaan berikutnya.")
                except Exception as e:
                    print(f"[WARN] Gagal menyuntikkan eksternal ke history: {e}")

                final_answer = external_result
        else:
            # Local Answer
            final_answer = answer
            
        return jsonify({"response": final_answer})

    except Exception as e:
        print(f"Error processing chat: {e}")
        return jsonify({"error": str(e)}), 500

def init_app():
    global model, dataset_context
    check_dependencies()
    # genai.configure(api_key=API_KEY)
    genai.configure(api_key=API_KEYS[0]) # Use first key default
    
    print("[LAYER 1] Memuat Database Lokal (MySQL)...", end='')
    dataset_context = load_from_mysql()
    print(" Selesai.")

    try:
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=SYSTEM_INSTRUCTION
        )
        print("[READY] Model initialized.")
    except Exception as e:
        print(f"\n[FATAL] Gagal init model: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
