let currentMap = null;
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
