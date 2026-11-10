import os, json, logging, re
import markdown
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
logging.basicConfig(level=logging.INFO)

os.makedirs(Config.PHOTOS_FOLDER, exist_ok=True)
os.makedirs(Config.ANALYSIS_RESULTS_FOLDER, exist_ok=True)

IMG_EXT = ('.png', '.jpg', '.jpeg', '.tiff', '.webp', '.bmp')

@app.route('/')
def index():
    photos = []
    if os.path.exists(Config.PHOTOS_FOLDER):
        photos = [f for f in os.listdir(Config.PHOTOS_FOLDER) if f.lower().endswith(IMG_EXT)]
    return render_template('index.html', photos=photos)

@app.route('/photos/<filename>')
def photo_file(filename):
    return send_from_directory(Config.PHOTOS_FOLDER, filename)

# НОВИЙ МАРШРУТ ДЛЯ ЗАВАНТАЖЕННЯ
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Немає файлу'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не обрано'}), 400
        
    if file and file.filename.lower().endswith(IMG_EXT):
        filename = secure_filename(file.filename)
        # Якщо файл з такою назвою вже є, додаємо суфікс
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(os.path.join(Config.PHOTOS_FOLDER, filename)):
            filename = f"{base}_{counter}{ext}"
            counter += 1
            
        file.save(os.path.join(Config.PHOTOS_FOLDER, filename))
        return jsonify({'status': 'ok', 'filename': filename})
        
    return jsonify({'error': 'Непідтримуваний формат файлу'}), 400

@app.route('/analyze/<filename>', methods=['POST'])
def analyze(filename):
    path = os.path.join(Config.PHOTOS_FOLDER, filename)
    if not os.path.exists(path):
        return jsonify({'error': 'Файл не знайдено'}), 404
    try:
        results = analyze_photo(path, filename)
        
        report_path = os.path.join(Config.BASE_DIR, 'analysis', filename + '_intake', 'intake.md')
        report_html = ""
        report_text = ""
        if os.path.exists(report_path):
            with open(report_path, 'r', encoding='utf-8') as f:
                report_text = f.read()
                report_html = markdown.markdown(report_text, extensions=['tables', 'fenced_code'])

        ai_result = analyze_clues_with_ollama(path, report_text)
        
        return jsonify({
            'status': 'ok', 
            'report_html': report_html,
            'ai_options': [opt.dict() for opt in ai_result.suggestions]
        })
    except Exception as e:
        logging.exception('analyze failed')
        return jsonify({'error': str(e)}), 500

@app.route('/deep_search/<filename>', methods=['POST'])
def deep_search(filename):
    data = request.get_json() or {}
    lat = data.get('latitude')
    lon = data.get('longitude')
    
    if not lat or not lon:
        return jsonify({'error': 'Спочатку оберіть локацію на карті!'}), 400

    path = os.path.join(Config.PHOTOS_FOLDER, filename)
    try:
        geolocator = Nominatim(user_agent="geo_photo_locator_ai")
        location = geolocator.reverse(f"{lat}, {lon}")
        address = location.address if location else "Адресу не знайдено"
        
        deep_results = run_deep_scripts(path, filename, lat, lon)
        
        deep_report_html = f"<h5>Деталі локації:</h5>"
        deep_report_html += f"<p><b>Адреса:</b> {address}</p>"
        
        if deep_results.get('gsv', {}).get('success'):
            deep_report_html += "<p class='text-success'>✅ Панораму Google Street View знайдено!</p>"
        else:
            deep_report_html += "<p class='text-muted'>ℹ️ Панораму Street View для цієї точки не знайдено.</p>"
            
        return jsonify({'status': 'ok', 'deep_report_html': deep_report_html})
    except Exception as e:
        logging.exception('deep_search failed')
        return jsonify({'error': str(e)}), 500

@app.route('/confirm/<filename>', methods=['POST'])
def confirm(filename):
    data = request.get_json() or {}
    lat, lon = data.get('latitude'), data.get('longitude')
    location_name = data.get('location_name')
    learn = data.get('learn', False)
    
    if lat is None or lon is None:
        return jsonify({'error': 'Не вказано координати'}), 400
    
    path = os.path.join(Config.PHOTOS_FOLDER, filename)
    if not os.path.exists(path):
        return jsonify({'error': 'Файл не знайдено'}), 404
    
    ok = write_gps_to_exif(path, float(lat), float(lon))
    
    if ok:
        if learn and location_name:
            save_to_knowledge_base(location_name, float(lat), float(lon))
            return jsonify({'status': 'ok', 'message': f'GPS записано, локацію "{location_name}" додано до бази!'})
        return jsonify({'status': 'ok', 'message': 'GPS успішно записано в EXIF!'})
    return jsonify({'error': 'Не вдалося записати EXIF'}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
