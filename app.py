from dotenv import load_dotenv
import os
from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
import google.generativeai as genai
import json
import time
import re
from datetime import datetime
import logging
import zipfile

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

app = Flask(__name__)
CORS(app)

# Upload config
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
# Keep a set of document extensions allowed; images and videos are allowed by mimetype
ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'rtf', 'odt', 'zip'
}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Allow up to 20 MB uploads
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20 MB


@app.errorhandler(413)
def request_entity_too_large(error):
    logger.warning('Upload melebihi batas MAX_CONTENT_LENGTH')
    return jsonify({'success': False, 'response': 'File terlalu besar. Maksimum 20MB.'}), 413


def allowed_file(file_storage_or_name):
    """Accept any image/* or video/* MIME type, or allow certain document extensions.
    Accepts a Werkzeug FileStorage or a filename string.
    """
    # If a FileStorage is passed, inspect its mimetype first
    mimetype = None
    try:
        mimetype = getattr(file_storage_or_name, 'mimetype', None)
    except Exception:
        mimetype = None

    if mimetype and isinstance(mimetype, str):
        if mimetype.startswith('image/') or mimetype.startswith('video/'):
            return True

    # Fallback: check extension from filename
    if isinstance(file_storage_or_name, str):
        filename = file_storage_or_name
    else:
        filename = getattr(file_storage_or_name, 'filename', '')

    if not filename:
        return False

    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in ALLOWED_EXTENSIONS


class MultiLayerChatbot:
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("GEMINI_API_KEY tidak boleh kosong!")
        
        genai.configure(api_key=api_key)
        
        logger.info("Mencari model Gemini yang tersedia...")
        available_models = []
        
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
                    logger.info(f"Model tersedia: {m.name}")
        except Exception as e:
            logger.error(f"Error listing models: {e}")
        
        if not available_models:
            raise ValueError("Tidak ada model yang tersedia. Periksa API key!")
        
        model_name = available_models[0].replace('models/', '')
        
        try:
            self.model = genai.GenerativeModel(model_name)
            logger.info(f"Chatbot berhasil diinisialisasi dengan {model_name}")
        except Exception as e:
            raise ValueError(f"Gagal inisialisasi model {model_name}: {e}")
        
        self.chat_history = []
        self.conversation_memory = []  # Memory untuk context
        self.model_name = model_name
    
    def get_available_models(self):
        try:
            models = genai.list_models()
            available = []
            for model in models:
                if 'generateContent' in model.supported_generation_methods:
                    available.append({
                        'name': model.name,
                        'display_name': model.display_name,
                        'description': model.description[:100] if model.description else 'N/A'
                    })
            return available
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []
    
    def search_scholarly(self, query, max_results=3):
        try:
            from scholarly import scholarly
            import socket
            
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(10)
            
            logger.info(f"Mencari di Google Scholar: {query}")
            search_query = scholarly.search_pubs(query)
            results = []
            
            for i, pub in enumerate(search_query):
                if i >= max_results:
                    break
                    
                bib = pub.get('bib', {})
                results.append({
                    'title': bib.get('title', 'N/A'),
                    'author': ', '.join(bib.get('author', [])) if isinstance(bib.get('author'), list) else bib.get('author', 'N/A'),
                    'year': bib.get('pub_year', 'N/A'),
                    'abstract': bib.get('abstract', 'N/A'),
                    'citations': pub.get('num_citations', 0),
                    'venue': bib.get('venue', 'N/A')
                })
            
            socket.setdefaulttimeout(original_timeout)
            logger.info(f"Ditemukan {len(results)} referensi akademik")
            return results
            
        except ImportError:
            logger.warning("Module scholarly tidak terinstall")
            return []
        except Exception as e:
            logger.error(f"Error saat mencari di Scholar: {str(e)}")
            return []
    
    def build_conversation_context(self):
        """Build context dari conversation history"""
        if not self.conversation_memory:
            return ""
        
        # Ambil max 3 percakapan terakhir saja (lebih fokus)
        recent_convs = self.conversation_memory[-3:]
        
        context = "\n\nKONTEKS PERCAKAPAN SEBELUMNYA (untuk referensi saja):\n"
        
        for idx, conv in enumerate(recent_convs, 1):
            # Potong response yang terlalu panjang
            assistant_text = conv['assistant'][:200]
            if len(conv['assistant']) > 200:
                assistant_text += "..."
            
            context += f"\n[{idx}] User bertanya: {conv['user']}\n"
            context += f"    Kamu jawab: {assistant_text}\n"
        
        context += "\n(Gunakan konteks di atas HANYA jika pertanyaan baru merujuk ke percakapan sebelumnya)\n"
        context += "---\n"
        return context
    
    def create_enhanced_prompt(self, user_query, scholar_data):
        scholar_context = ""
        
        if scholar_data:
            scholar_context = "\n\nDATA REFERENSI AKADEMIK:\n"
            for idx, paper in enumerate(scholar_data, 1):
                scholar_context += f"\n[Referensi {idx}]\n"
                scholar_context += f"Judul: {paper['title']}\n"
                scholar_context += f"Penulis: {paper['author']}\n"
                scholar_context += f"Tahun: {paper['year']}\n"
                
                if paper['venue'] != 'N/A':
                    scholar_context += f"Publikasi: {paper['venue']}\n"
                
                if paper['abstract'] != 'N/A':
                    abstract = paper['abstract'][:500]
                    scholar_context += f"Abstrak: {abstract}...\n"
                
                scholar_context += f"Sitasi: {paper['citations']}\n"
        
        # Build conversation context
        conversation_context = self.build_conversation_context()
        
        prompt = f"""Kamu adalah asisten AI pertanian yang cerdas dan membantu. Kamu berbicara dengan gaya natural dan santai seperti teman.

PERSONA DAN TONE:
- Panggil user dengan "kamu" (bukan Bapak/Ibu/Anda)
- Gunakan bahasa yang friendly dan approachable
- Seperti kakak yang care dan mau bantu
- Tetap profesional tapi tidak kaku
- Hangat dan supportif

PENTING - ATURAN FORMATTING:
- JANGAN gunakan markdown formatting seperti **bold**, *italic*, atau ### headers
- JANGAN gunakan bullet points dengan bintang (*)
- Tulis dalam paragraf natural seperti sedang berbicara
- Gunakan angka (1, 2, 3) atau dash (-) untuk list jika memang perlu
- Pisahkan topik dengan baris kosong, bukan dengan header berbintang
- Tulis teks polos biasa, natural seperti chat

CARA MENJAWAB:
- Fokus HANYA pada pertanyaan terakhir yang baru ditanyakan
- Jangan jawab ulang pertanyaan lama dari history
- Gunakan context sebelumnya HANYA jika pertanyaan baru merujuknya (misal: "yang tadi", "poin nomor 2", "itu maksudnya gimana")
- Jika pertanyaan baru sama sekali berbeda dari history, jawab fresh tanpa nyambung-nyambungin
- Gunakan bahasa yang santai tapi informatif
- Tulis seperti sedang menjelaskan ke teman
- Berikan informasi yang akurat dan faktual
- Jika ada data dari referensi, sebutkan dengan natural
- Berikan contoh konkret agar mudah dipahami
- Fokus pada solusi praktis untuk petani

{conversation_context}

{scholar_context}

PERTANYAAN BARU DARI USER (FOKUS JAWAB INI): {user_query}

Jawab dengan natural, informatif, dan helpful. Ingat: JANGAN pakai format markdown apapun! Jawab dengan gaya ngobrol santai tapi tetap memberikan info yang berguna. FOKUS HANYA PADA PERTANYAAN TERAKHIR!"""

        return prompt
    
    def clean_response_text(self, text):
        """Membersihkan text dari formatting markdown"""
        cleaned = text
        
        # Hapus bold markdown (**text**)
        cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)
        
        # Hapus italic markdown (*text*)
        cleaned = re.sub(r'(?<!\*)\*(?!\*)([^*]+)\*(?!\*)', r'\1', cleaned)
        
        # Hapus headers markdown (### text)
        cleaned = re.sub(r'^#{1,6}\s+', '', cleaned, flags=re.MULTILINE)
        
        # Replace bullet points dengan dash
        cleaned = cleaned.replace('\n*   ', '\n- ')
        cleaned = cleaned.replace('\n* ', '\n- ')
        cleaned = cleaned.replace('\n• ', '\n- ')
        
        # Bersihkan multiple newlines (max 2 baris kosong)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        # Trim whitespace di awal dan akhir
        cleaned = cleaned.strip()
        
        return cleaned
    
    def get_response(self, user_query, use_scholar=False):
        scholar_data = []
        start_time = time.time()
        
        if use_scholar:
            try:
                scholar_data = self.search_scholarly(user_query)
            except Exception as e:
                logger.error(f"Error pada Scholar search: {e}")
        
        enhanced_prompt = self.create_enhanced_prompt(user_query, scholar_data)
        
        try:
            logger.info("Gemini sedang memproses...")
            
            response = self.model.generate_content(
                enhanced_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    top_p=0.95,
                    top_k=40,
                    max_output_tokens=2048,
                )
            )
            
            if not response or not response.text:
                raise ValueError("Response kosong dari Gemini")
            
            # Clean formatting
            cleaned_text = self.clean_response_text(response.text)
            
            # Simpan ke conversation memory
            self.conversation_memory.append({
                'user': user_query,
                'assistant': cleaned_text,
                'timestamp': datetime.now().isoformat()
            })
            
            processing_time = time.time() - start_time
            
            # Simpan ke chat history (untuk logging)
            self.chat_history.append({
                'timestamp': datetime.now().isoformat(),
                'query': user_query,
                'scholar_refs': len(scholar_data),
                'response': cleaned_text,
                'processing_time': round(processing_time, 2)
            })
            
            logger.info(f"Response berhasil ({processing_time:.2f}s)")
            
            return {
                'success': True,
                'response': cleaned_text,
                'scholar_data': scholar_data,
                'has_references': len(scholar_data) > 0,
                'references_count': len(scholar_data),
                'processing_time': round(processing_time, 2),
                'conversation_length': len(self.conversation_memory)
            }
            
        except Exception as e:
            logger.error(f"Error saat generate response: {str(e)}")
            return {
                'success': False,
                'response': f"Maaf, terjadi kesalahan: {str(e)}",
                'scholar_data': [],
                'has_references': False,
                'error': str(e)
            }
    
    def clear_history(self):
        self.chat_history = []
        self.conversation_memory = []
        logger.info("Riwayat chat dan memory telah dihapus")
    
    def export_history(self, filename='chat_history.json'):
        try:
            export_data = {
                'chat_history': self.chat_history,
                'conversation_memory': self.conversation_memory,
                'exported_at': datetime.now().isoformat()
            }
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            logger.info(f"History exported to {filename}")
            return filename
        except Exception as e:
            logger.error(f"Error exporting history: {e}")
            raise


# Initialize chatbot
chatbot = None

try:
    if GEMINI_API_KEY:
        chatbot = MultiLayerChatbot(GEMINI_API_KEY)
    else:
        logger.error("GEMINI_API_KEY tidak ditemukan!")
except Exception as e:
    logger.error(f"Error inisialisasi chatbot: {e}")


# Flask Routes
@app.route('/')
def home():
    try:
        return send_from_directory('.', 'smartani.html')
    except FileNotFoundError:
        return jsonify({'error': 'smartani.html tidak ditemukan'}), 404


@app.route('/<path:filename>')
def serve_static(filename):
    try:
        return send_from_directory('.', filename)
    except FileNotFoundError:
        return jsonify({'error': f'File {filename} tidak ditemukan'}), 404


@app.route('/api/chat', methods=['POST'])
def chat():
    if not chatbot:
        return jsonify({
            'success': False,
            'response': 'Chatbot belum diinisialisasi. Periksa GEMINI_API_KEY'
        }), 500
    
    try:
        # Support both JSON (text-only) and multipart/form-data (with file)
        message = ''
        use_scholar = False

        if request.content_type and request.content_type.startswith('multipart/form-data'):
            # form with possible file
            message = request.form.get('message', '').strip()
            use_scholar = request.form.get('use_scholar', 'false').lower() == 'true'

            # Handle file if present
            file = request.files.get('file')
            file_url = None
            if file and file.filename:
                # Pass the FileStorage object so allowed_file can check mimetype (image/*)
                if allowed_file(file):
                    filename = secure_filename(f"{int(time.time())}_{file.filename}")
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(save_path)
                    # Build URL for the saved file
                    file_url = url_for('uploaded_file', filename=filename, _external=False)
                else:
                    return jsonify({'success': False, 'response': 'Tipe file tidak diizinkan'}), 400

            # If the uploaded file is a zip, optionally list its contents (do not extract)
            zip_contents = None
            try:
                if file_url and filename.lower().endswith('.zip'):
                    try:
                        with zipfile.ZipFile(save_path, 'r') as zf:
                            # Limit list to first 200 entries to avoid huge responses
                            zip_contents = zf.namelist()[:200]
                    except Exception as ze:
                        logger.warning(f"Gagal membaca zip contents: {ze}")

            if not message and not file_url:
                return jsonify({'success': False, 'response': 'Pesan atau file harus disertakan'}), 400

            # If file uploaded, prepend a note to message so the chatbot can consider it if needed
            if file_url:
                message = f"[FILE_UPLOADED:{file_url}] {message}"

            result = chatbot.get_response(message, use_scholar=use_scholar)
            # Include file metadata in response
            if zip_contents is not None:
                result.update({'file_url': file_url, 'zip_contents': zip_contents})
            else:
                result.update({'file_url': file_url})
            return jsonify(result)
        else:
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'response': 'Request body kosong'
                }), 400

            message = data.get('message', '').strip()
            use_scholar = data.get('use_scholar', False)

            if not message:
                return jsonify({
                    'success': False,
                    'response': 'Pesan tidak boleh kosong'
                }), 400

            result = chatbot.get_response(message, use_scholar=use_scholar)
            return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error di /api/chat: {str(e)}")
        return jsonify({
            'success': False,
            'response': f'Terjadi kesalahan server: {str(e)}'
        }), 500


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except FileNotFoundError:
        return jsonify({'error': 'File tidak ditemukan'}), 404


@app.route('/api/history', methods=['GET'])
def get_history():
    if not chatbot:
        return jsonify({'error': 'Chatbot belum diinisialisasi'}), 500
    
    return jsonify({
        'success': True,
        'history': chatbot.chat_history,
        'conversation_memory': chatbot.conversation_memory,
        'total_chats': len(chatbot.chat_history),
        'memory_length': len(chatbot.conversation_memory)
    })


@app.route('/api/history', methods=['DELETE'])
def clear_history():
    if not chatbot:
        return jsonify({'error': 'Chatbot belum diinisialisasi'}), 500
    
    try:
        chatbot.clear_history()
        return jsonify({
            'success': True,
            'message': 'Riwayat chat dan memory berhasil dihapus'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/export', methods=['GET'])
def export_history():
    if not chatbot:
        return jsonify({'error': 'Chatbot belum diinisialisasi'}), 500
    
    try:
        filename = chatbot.export_history()
        return jsonify({
            'success': True,
            'message': f'Riwayat berhasil diexport ke {filename}',
            'filename': filename
        })
    except Exception as e:
        logger.error(f"Error export: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/status', methods=['GET'])
def status():
    available_models = []
    if chatbot:
        available_models = chatbot.get_available_models()
    
    return jsonify({
        'success': True,
        'status': 'online',
        'chatbot_ready': chatbot is not None,
        'api_key_configured': GEMINI_API_KEY is not None,
        'total_chats': len(chatbot.chat_history) if chatbot else 0,
        'memory_length': len(chatbot.conversation_memory) if chatbot else 0,
        'available_models': available_models[:5],
        'timestamp': datetime.now().isoformat()
    })


@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint tidak ditemukan'}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("SMARTANI - CHATBOT PERTANIAN AI (Enhanced)")
    print("=" * 60)
    print(f"Server: http://localhost:5001")
    print(f"API Key: {'✓ OK' if GEMINI_API_KEY else '✗ NOT FOUND'}")
    print(f"Model: {chatbot.model_name if chatbot else 'Not initialized'}")
    print(f"CORS: Enabled")
    print(f"Features: Memory ✓ | Clean Format ✓ | Friendly Tone ✓")
    print("=" * 60)
    print("\nEndpoints:")
    print("  GET  /              - Serve smartani.html")
    print("  POST /api/chat      - Kirim pesan ke chatbot")
    print("  GET  /api/history   - Lihat riwayat chat + memory")
    print("  DELETE /api/history - Hapus riwayat chat + memory")
    print("  GET  /api/export    - Export riwayat ke JSON")
    print("  GET  /api/status    - Cek status server")
    print("=" * 60 + "\n")
    
    if not GEMINI_API_KEY:
        print("⚠ WARNING: GEMINI_API_KEY tidak ditemukan!")
        print("Buat file .env dan tambahkan: GEMINI_API_KEY=your_key\n")
    
    app.run(host='0.0.0.0', port=5001, debug=True)