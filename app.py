import os, json, logging, time
import markdown
import ollama
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from config import Config
from utils.geo_sleuth_runner import analyze_photo
from utils.exif_writer import write_gps_to_exif
from utils.ollama_helper import analyze_clues_with_ollama, save_to_knowledge_base
from utils.deep_search_runner import run_deep_scripts
from geopy.geocoders import Nominatim

app = Flask(__name__)
app.config.from_object(Config)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

os.makedirs(Config.PHOTOS_FOLDER, exist_ok=True)
os.makedirs(Config.ANALYSIS_RESULTS_FOLDER, exist_ok=True)

IMG_EXT = ('.png', '.jpg', '.jpeg', '.tiff', '.webp', '.bmp')
geolocator = Nominatim(user_agent="geo_photo_locator_ai")

# Словник для зберігання статусів аналізу
analysis_status = {}

@app.route('/')
def index():
    photos = []
    if os.path.exists(Config.PHOTOS_FOLDER):
        photos = [f for f in os.listdir(Config.PHOTOS_FOLDER) if f.lower().endswith(IMG_EXT)]
    return render_template('index.html', photos=photos, model_name=Config.OLLAMA_MODEL)

@app.route('/api/model_status')
def model_status():
    model_name = Config.OLLAMA_MODEL
    result = {"ollama_online": False, "model": model_name, "model_loaded": False, "latency": None, "status": "error", "error": None}
    try:
        models_info = ollama.list()
        result["ollama_online"] = True
        models = models_info.get('models', []) if isinstance(models_info, dict) else getattr(models_info, 'models', [])
        found = any(model_name in (m.get('name', '') if isinstance(m, dict) else getattr(m, 'name', getattr(m, 'model', ''))) for m in models)
        if found:
            result["model_loaded"] = True
            start_time = time.time()
            ollama.chat(model=model_name, messages=[{'role': 'user', 'content': 'hi'}], options={'num_predict': 1})
            result["latency"] = round(time.time() - start_time, 2)
            result["status"] = "healthy"
        else:
            result["status"] = "missing"
            result["error"] = f"Модель '{model_name}' не знайдена."
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return jsonify(result)

@app.route('/photos/<filename>')
def photo_file(filename):
    return send_from_directory(Config.PHOTOS_FOLDER, filename)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': 'Немає файлу'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'Файл не обрано'}), 400
    if file and file.filename.lower().endswith(IMG_EXT):
        filename = secure_filename(file.filename)
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(os.path.join(Config.PHOTOS_FOLDER, filename)):
            filename = f"{base}_{counter}{ext}"
            counter += 1
        file.save(os.path.join(Config.PHOTOS_FOLDER, filename))
        return jsonify({'status': 'ok', 'filename': filename})
    return jsonify({'error': 'Непідтримуваний формат'}), 400

@app.route('/analyze/<filename>', methods=['POST'])
def analyze(filename):
    logging.info(f"--- ПОЧАТОК АНАЛІЗУ: {filename} ---")
    path = os.path.join(Config.PHOTOS_FOLDER, filename)
    if not os.path.exists(path): return jsonify({'error': 'Файл не знайдено'}), 404
    
    analysis_status[filename] = {'status': 'processing', 'result': None, 'error': None}
    
    import threading
    def run_analysis():
        try:
            logging.info("Крок 1: Запуск geo-sleuth...")
            results = analyze_photo(path, filename)
            
            logging.info("Крок 2: Читання звіту...")
            report_path = os.path.join(Config.BASE_DIR, 'analysis', filename + '_intake', 'intake.md')
            report_html = ""
            report_text = ""
            if os.path.exists(report_path):
                with open(report_path, 'r', encoding='utf-8') as f:
                    report_text = f.read()
                    report_html = markdown.markdown(report_text, extensions=['tables', 'fenced_code'])

            logging.info("Крок 3: Відправка в Ollama...")
            ai_result = analyze_clues_with_ollama(path, report_text)
            
            analysis_status[filename] = {
                'status': 'done',
                'result': {
                    'report_html': report_html,
                    'ai_options': [opt.model_dump() for opt in ai_result.suggestions]
                },
                'error': None
            }
            logging.info("Крок 4: Успіх! Результат збережено.")
        except Exception as e:
            logging.error(f"ПОМИЛКА: {str(e)}")
            analysis_status[filename] = {'status': 'error', 'result': None, 'error': str(e)}

    thread = threading.Thread(target=run_analysis)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started', 'message': 'Аналіз розпочато'})

@app.route('/check_status/<filename>', methods=['GET'])
def check_status(filename):
    status = analysis_status.get(filename)
    if not status:
        return jsonify({'status': 'not_found'})
    return jsonify(status)

@app.route('/deep_search/<filename>', methods=['POST'])
def deep_search(filename):
    data = request.get_json() or {}
    lat, lon = data.get('latitude'), data.get('longitude')
    if not lat or not lon: return jsonify({'error': 'Спочатку оберіть локацію на карті!'}), 400
    path = os.path.join(Config.PHOTOS_FOLDER, filename)
    try:
        location = geolocator.reverse(f"{lat}, {lon}")
        address = location.address if location else "Адресу не знайдено"
        deep_results = run_deep_scripts(path, filename, lat, lon)
        deep_report_html = f"<h5>Деталі локації:</h5><p><b>Адреса:</b> {address}</p>"
        return jsonify({'status': 'ok', 'deep_report_html': deep_report_html})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/confirm/<filename>', methods=['POST'])
def confirm(filename):
    data = request.get_json() or {}
    lat, lon, location_name, learn = data.get('latitude'), data.get('longitude'), data.get('location_name'), data.get('learn', False)
    if lat is None or lon is None: return jsonify({'error': 'Не вказано координати'}), 400
    path = os.path.join(Config.PHOTOS_FOLDER, filename)
    if write_gps_to_exif(path, float(lat), float(lon)):
        if learn and location_name:
            save_to_knowledge_base(location_name, float(lat), float(lon))
            return jsonify({'status': 'ok', 'message': f'GPS записано, локацію "{location_name}" додано!'})
        return jsonify({'status': 'ok', 'message': 'GPS успішно записано в EXIF!'})
    return jsonify({'error': 'Не вдалося записати EXIF'}), 500

if __name__ == '__main__':
    # ВИКОРИСТОВУЄМО ПОРТ 9874 (як у вашому start.bat)
    app.run(host='127.0.0.1', port=9874, debug=True, threaded=True)
