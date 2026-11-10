import os

base_dir = os.path.dirname(os.path.abspath(__file__))

print("⏳ Додавання функції завантаження фото...")

files = {
    # Повертаємо папку назад
    "config.py": """import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-me')
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    PHOTOS_FOLDER = os.path.join(BASE_DIR, 'photos')
    GEO_SLEUTH_PATH = os.path.join(BASE_DIR, 'geo-sleuth', 'skills', 'geo-sleuth', 'scripts')
    ANALYSIS_RESULTS_FOLDER = os.path.join(BASE_DIR, 'analysis', 'results')
    GEO_SLEUTH_TIMEOUT = 900
    USE_OLLAMA = os.getenv('USE_OLLAMA', 'True').lower() == 'true'
    OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llava')
""",
    
    # Додаємо маршрут для завантаження на бекенді
    "app.py": """import os, json, logging, re
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
""",
    
    # Додаємо Drag & Drop зону у HTML
    "templates/index.html": """{% extends 'base.html' %}
{% block content %}
<h3 class='mb-3'>Фото у папці photos/</h3>

<!-- Зона для завантаження -->
<div id="dropzone" class="mb-4 p-5 text-center bg-light border border-2 border-dashed rounded" style="cursor: pointer; border-color: #ccc;">
    <h4>📸 Перетягніть фото сюди або натисніть</h4>
    <p class="text-muted mb-0">Підтримуються JPG, PNG, WEBP</p>
    <input type="file" id="fileInput" class="d-none" accept="image/*">
</div>

<div class='row' id="photo-grid">
{% for p in photos %}
  <div class='col-md-4 mb-4'>
    <div class='card h-100 shadow-sm'>
      <div class="analyze" data-file="{{ p }}" style="cursor: pointer;" title="Натисніть, щоб проаналізувати">
        <img src='{{ url_for("photo_file", filename=p) }}' class='card-img-top' style='height:220px;object-fit:cover'>
      </div>
      <div class='card-body d-flex flex-column'>
        <h6 class='text-truncate'>{{ p }}</h6>
        <button class='btn btn-primary btn-sm mt-auto analyze' data-file='{{ p }}'>Аналізувати</button>
      </div>
    </div>
  </div>
{% else %}
  <p class='text-muted'>Папка photos/ порожня. Додайте зображення.</p>
{% endfor %}
</div>

<!-- Модальне вікно -->
<div class='modal fade' id='resultModal' tabindex='-1'>
  <div class='modal-dialog modal-xl'>
    <div class='modal-content'>
      <div class='modal-header'>
        <h5 class='modal-title'>Аналіз: <span id='modal-filename'></span></h5>
        <button type='button' class='btn-close' data-bs-dismiss='modal'></button>
      </div>
      <div class='modal-body'>
        <div class='row'>
          <div class='col-md-5'>
            <img id='modal-img' src='' class='img-fluid rounded shadow mb-3'>
            <div id='map' style='height:300px' class='rounded border'></div>
          </div>
          <div class='col-md-7 d-flex flex-column'>
            <div id='ai-suggestions-container'></div>
            <div id="deep-search-results" style="display:none;" class="alert alert-info mt-2"></div>
            <h6 class='text-muted mt-3'>Детальний звіт скриптів:</h6>
            <pre id='modal-output' class='flex-grow-1 bg-light p-3 border rounded' style='max-height: 300px; overflow-y: auto; font-size: 0.8rem;'></pre>
          </div>
        </div>
      </div>
      <div class='modal-footer bg-light d-block'>
        <div class='row g-2 align-items-center'>
          <div class='col-md-3'><input type='text' id='loc-name' class='form-control form-control-sm' placeholder='Назва (для навчання)'></div>
          <div class='col-md-2'><input type='text' id='lat' class='form-control form-control-sm' placeholder='Широта'></div>
          <div class='col-md-2'><input type='text' id='lon' class='form-control form-control-sm' placeholder='Довгота'></div>
          <div class='col-md-2'>
            <div class='form-check'>
              <input class='form-check-input' type='checkbox' id='learn-check' checked>
              <label class='form-check-label small' for='learn-check'>Запам'ятати</label>
            </div>
          </div>
          <div class='col-md-3 text-end'>
            <button type='button' class='btn btn-warning btn-sm me-2' id='deep-search-btn' style='display:none;'>🔍 Глибокий пошук</button>
            <button type='button' class='btn btn-outline-danger btn-sm' data-bs-dismiss='modal'>Ні</button>
            <button type='button' class='btn btn-success btn-sm px-4' id='confirm-btn'>Так, записати</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
{% endblock %}
""",
    
    # Оновлюємо JS: робимо функцію analyzeImage та додаємо логіку Drag & Drop
    "static/js/app.js": """let currentMap = null;
let currentMarker = null;
let currentFilename = '';

async function safeFetch(url, options = {}) {
    try {
        const response = await fetch(url, options);
        const text = await response.text();
        try { return JSON.parse(text); } 
        catch (e) { return { error: "Помилка формату JSON" }; }
    } catch (e) { return { error: "Помилка мережі: " + e.message }; }
}

// --- ЛОГІКА DRAG & DROP ---
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');

dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('bg-warning');
});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('bg-warning'));
dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('bg-warning');
    if (e.dataTransfer.files.length) handleUpload(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => {
    if (fileInput.files.length) handleUpload(fileInput.files[0]);
});

async function handleUpload(file) {
    const originalHtml = dropzone.innerHTML;
    dropzone.innerHTML = '<div class="spinner-border text-primary"></div> Завантаження...';
    
    const formData = new FormData();
    formData.append('file', file);

    const d = await safeFetch('/upload', { method: 'POST', body: formData });
    
    if (d.error) {
        alert('Помилка завантаження: ' + d.error);
        dropzone.innerHTML = originalHtml;
    } else {
        // Додаємо нову картку в сітку і відразу запускаємо аналіз
        window.location.reload(); 
        setTimeout(() => {
            // Після перезавантаження можна відразу знайти файл і клікнути на нього
            // Але для простоти краще хай користувач сам клікне
        }, 500);
    }
}
// --------------------------

function analyzeImage(file) {
    currentFilename = file;
    
    document.getElementById('modal-filename').textContent = file;
    document.getElementById('modal-img').src = '/photos/' + encodeURIComponent(file);
    document.getElementById('modal-output').textContent = 'Аналіз...';
    document.getElementById('ai-suggestions-container').innerHTML = '<div class="spinner-border text-primary" role="status"></div> ШІ аналізує підказки...';
    document.getElementById('lat').value = '';
    document.getElementById('lon').value = '';
    document.getElementById('loc-name').value = '';
    document.getElementById('deep-search-btn').style.display = 'none';
    document.getElementById('deep-search-results').style.display = 'none';
    
    if (!currentMap) {
      currentMap = L.map('map').setView([49.8397, 24.0297], 10);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(currentMap);
      currentMap.on('click', e => {
        document.getElementById('lat').value = e.latlng.lat.toFixed(6);
        document.getElementById('lon').value = e.latlng.lng.toFixed(6);
        if (currentMarker) currentMarker.setLatLng(e.latlng);
        else currentMarker = L.marker(e.latlng).addTo(currentMap);
        document.getElementById('deep-search-btn').style.display = 'inline-block';
      });
    }
    
    if (currentMarker) { currentMap.removeLayer(currentMarker); currentMarker = null; }
    
    const modal = new bootstrap.Modal(document.getElementById('resultModal'));
    modal.show();
    setTimeout(() => { if(currentMap) currentMap.invalidateSize(); }, 300);

    safeFetch('/analyze/' + encodeURIComponent(file), { method: 'POST' }).then(d => {
        if (d.error) {
            document.getElementById('ai-suggestions-container').innerHTML = '<span class="text-danger">' + d.error + '</span>';
            return;
        }
        
        const cont = document.getElementById('ai-suggestions-container');
        cont.innerHTML = '<h6 class="text-success mb-2">🤖 ШІ пропонує варіанти:</h6>';
        
        if (d.ai_options && d.ai_options.length > 0) {
            d.ai_options.forEach((opt, idx) => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-outline-success w-100 text-start mb-2 p-3 shadow-sm';
                const conf = opt.confidence ? ` (Впевненість: ${(opt.confidence*100).toFixed(0)}%)` : '';
                btn.innerHTML = `<b>${opt.name}</b>${conf}<br><small class="text-muted">${opt.reasoning}</small>`;
                btn.onclick = () => {
                    cont.querySelectorAll('button').forEach(b => b.classList.remove('active', 'bg-success', 'text-white'));
                    btn.classList.add('active', 'bg-success', 'text-white');
                    
                    document.getElementById('lat').value = opt.lat.toFixed(6);
                    document.getElementById('lon').value = opt.lon.toFixed(6);
                    document.getElementById('loc-name').value = opt.name;
                    
                    currentMap.setView([opt.lat, opt.lon], 15);
                    if (currentMarker) currentMarker.setLatLng([opt.lat, opt.lon]);
                    else currentMarker = L.marker([opt.lat, opt.lon]).addTo(currentMap);
                    
                    document.getElementById('deep-search-btn').style.display = 'inline-block';
                };
                cont.appendChild(btn);
            });
        }
        document.getElementById('modal-output').innerHTML = d.report_html || 'Звіт порожній.';
    });
}

// Прив'язуємо клік до всіх кнопок та картинок
document.querySelectorAll('.analyze').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    analyzeImage(btn.dataset.file);
  });
});

document.getElementById('deep-search-btn').addEventListener('click', async () => {
    const file = currentFilename;
    const lat = document.getElementById('lat').value;
    const lon = document.getElementById('lon').value;
    
    if (!lat || !lon) { alert('Спочатку оберіть локацію!'); return; }
    
    const deepBtn = document.getElementById('deep-search-btn');
    const originalText = deepBtn.innerHTML;
    deepBtn.disabled = true;
    deepBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Пошук...';
    
    const d = await safeFetch('/deep_search/' + encodeURIComponent(file), { 
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ latitude: parseFloat(lat), longitude: parseFloat(lon) })
    });
    
    if (d.error) { alert('Помилка: ' + d.error); } 
    else {
        const deepDiv = document.getElementById('deep-search-results');
        deepDiv.style.display = 'block';
        deepDiv.innerHTML = d.deep_report_html;
    }
    
    deepBtn.disabled = false;
    deepBtn.innerHTML = originalText;
});

document.getElementById('confirm-btn').addEventListener('click', async () => {
  const lat = document.getElementById('lat').value;
  const lon = document.getElementById('lon').value;
  const locName = document.getElementById('loc-name').value;
  const learn = document.getElementById('learn-check').checked;
  
  if (!lat || !lon) { alert('Оберіть варіант ШІ або клікніть на карту!'); return; }
  
  const d = await safeFetch('/confirm/' + encodeURIComponent(currentFilename), {
    method: 'POST', 
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ latitude: parseFloat(lat), longitude: parseFloat(lon), location_name: locName, learn: learn })
  });
  
  if (d.status === 'ok') {
    alert('Успіх: ' + d.message);
    bootstrap.Modal.getInstance(document.getElementById('resultModal')).hide();
  } else { alert('Помилка: ' + (d.error || 'Невідома')); }
});
"""
}

for filepath, content in files.items():
    full_path = os.path.join(base_dir, filepath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Оновлено: {filepath}")

# Додаємо стиль для пунктирної рамки в CSS, якщо його немає
css_path = os.path.join(base_dir, 'static', 'css', 'style.css')
if os.path.exists(css_path):
    with open(css_path, 'a', encoding='utf-8') as f:
        f.write("\n.border-dashed { border-style: dashed !important; }\n")

print("\n🎉 ГОТОВО! Додано зону Drag & Drop для завантаження фото.")
print("Перезапустіть сервер (python app.py) та оновіть сторінку (Ctrl+F5).")