let currentMap = null;
let currentMarker = null;
let currentFilename = '';
let pollingInterval = null;
let timerInterval = null;
let progressSeconds = 0;

// АВТОМАТИЧНЕ ВИЗНАЧЕННЯ ПОРТУ
const API_BASE = window.location.origin;

async function safeFetch(url, options = {}) {
    try {
        const response = await fetch(API_BASE + url, options);
        const text = await response.text();
        try { return JSON.parse(text); } 
        catch (e) { 
            console.error("Server returned non-JSON:", text);
            return { error: "Сервер повернув HTML замість JSON." }; 
        }
    } catch (e) { return { error: "Помилка мережі: " + e.message }; }
}

document.addEventListener('DOMContentLoaded', () => {
    const statusWidget = document.getElementById('ai-status-widget');
    if (statusWidget) {
        safeFetch('/api/model_status').then(data => {
            if (data.status === 'healthy') {
                statusWidget.className = 'badge bg-success p-2';
                statusWidget.innerHTML = `🟢 Ollama: OK | Модель: <b>${data.model}</b> | Відповідь: ${data.latency}с`;
            } else {
                statusWidget.className = 'badge bg-danger p-2';
                statusWidget.innerHTML = `🔴 Помилка Ollama`;
                statusWidget.setAttribute('title', data.error || 'Невідома помилка');
                new bootstrap.Tooltip(statusWidget);
            }
        });
    }

    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    if (dropzone && fileInput) {
        dropzone.addEventListener('click', () => fileInput.click());
        dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('bg-warning'); });
        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('bg-warning'));
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('bg-warning');
            if (e.dataTransfer.files.length) handleUpload(e.dataTransfer.files[0]);
        });
        fileInput.addEventListener('change', () => { if (fileInput.files.length) handleUpload(fileInput.files[0]); });
    }

    async function handleUpload(file) {
        const originalHtml = dropzone.innerHTML;
        dropzone.innerHTML = '<div class="spinner-border text-primary"></div> Завантаження...';
        const formData = new FormData();
        formData.append('file', file);
        const d = await safeFetch('/upload', { method: 'POST', body: formData });
        if (d.error) {
            alert('Помилка завантаження: ' + d.error);
            dropzone.innerHTML = originalHtml;
        } else { window.location.reload(); }
    }

    document.querySelectorAll('.analyze').forEach(btn => {
        btn.addEventListener('click', (e) => { e.preventDefault(); analyzeImage(btn.dataset.file); });
    });

    function startProgress(container) {
        progressSeconds = 0;
        container.innerHTML = `
            <div class="spinner-border text-primary mb-2" role="status"></div>
            <div><b>Локальна ШІ аналізує фото...</b></div>
            <div class="text-muted small">Модель працює на вашому ноутбуці. Це може зайняти до 10 хвилин.</div>
            <div class="mt-2 font-monospace" id="timer-display">Минуло: 0 сек</div>
        `;
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            progressSeconds++;
            const timerEl = document.getElementById('timer-display');
            if (timerEl) timerEl.textContent = `Минуло: ${progressSeconds} сек`;
        }, 1000);
    }

    function stopProgress() {
        if (timerInterval) clearInterval(timerInterval);
        if (pollingInterval) clearInterval(pollingInterval);
    }

    function analyzeImage(file) {
        currentFilename = file;
        document.getElementById('modal-filename').textContent = file;
        document.getElementById('modal-img').src = '/photos/' + encodeURIComponent(file);
        document.getElementById('modal-output').textContent = 'Аналіз...';
        
        const cont = document.getElementById('ai-suggestions-container');
        startProgress(cont);
        
        document.getElementById('lat').value = '';
        document.getElementById('lon').value = '';
        document.getElementById('loc-name').value = '';
        
        const deepBtn = document.getElementById('deep-search-btn');
        if (deepBtn) deepBtn.style.display = 'none';
        document.getElementById('deep-search-results').style.display = 'none';
        
        if (!currentMap) {
            currentMap = L.map('map').setView([49.8397, 24.0297], 10);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(currentMap);
            currentMap.on('click', e => {
                document.getElementById('lat').value = e.latlng.lat.toFixed(6);
                document.getElementById('lon').value = e.latlng.lng.toFixed(6);
                if (currentMarker) currentMarker.setLatLng(e.latlng);
                else currentMarker = L.marker(e.latlng).addTo(currentMap);
                if (deepBtn) deepBtn.style.display = 'inline-block';
            });
        }
        
        if (currentMarker) { currentMap.removeLayer(currentMarker); currentMarker = null; }
        const modal = new bootstrap.Modal(document.getElementById('resultModal'));
        modal.show();
        setTimeout(() => { if(currentMap) currentMap.invalidateSize(); }, 300);

        safeFetch('/analyze/' + encodeURIComponent(file), { method: 'POST' }).then(d => {
            if (d.error) {
                stopProgress();
                cont.innerHTML = '<span class="text-danger">' + d.error + '</span>';
                return;
            }
            
            pollingInterval = setInterval(async () => {
                const status = await safeFetch('/check_status/' + encodeURIComponent(file));
                
                if (status.status === 'done') {
                    stopProgress();
                    cont.innerHTML = '<h6 class="text-success mb-2">🤖 ШІ пропонує варіанти:</h6>';
                    if (status.result.ai_options && status.result.ai_options.length > 0) {
                        status.result.ai_options.forEach((opt) => {
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
                                if (deepBtn) deepBtn.style.display = 'inline-block';
                            };
                            cont.appendChild(btn);
                        });
                    }
                    document.getElementById('modal-output').innerHTML = status.result.report_html || 'Звіт порожній.';
                } else if (status.status === 'error') {
                    stopProgress();
                    cont.innerHTML = '<span class="text-danger">Помилка: ' + status.error + '</span>';
                }
            }, 3000);
        });
    }

    const deepBtn = document.getElementById('deep-search-btn');
    if (deepBtn) {
        deepBtn.addEventListener('click', async () => {
            const lat = document.getElementById('lat').value;
            const lon = document.getElementById('lon').value;
            if (!lat || !lon) { alert('Спочатку оберіть локацію!'); return; }
            const original = deepBtn.innerHTML;
            deepBtn.disabled = true;
            deepBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Пошук...';
            
            const d = await safeFetch('/deep_search/' + encodeURIComponent(currentFilename), {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ latitude: parseFloat(lat), longitude: parseFloat(lon) })
            });
            const div = document.getElementById('deep-search-results');
            div.style.display = 'block';
            div.innerHTML = d.error ? `<div class="alert alert-danger">Помилка: ${d.error}</div>` : d.deep_report_html;
            deepBtn.disabled = false;
            deepBtn.innerHTML = original;
        });
    }

    const confirmBtn = document.getElementById('confirm-btn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', async () => {
            const lat = document.getElementById('lat').value;
            const lon = document.getElementById('lon').value;
            if (!lat || !lon) { alert('Оберіть локацію!'); return; }
            
            const d = await safeFetch('/confirm/' + encodeURIComponent(currentFilename), {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ 
                    latitude: parseFloat(lat), 
                    longitude: parseFloat(lon), 
                    location_name: document.getElementById('loc-name').value, 
                    learn: document.getElementById('learn-check').checked 
                })
            });
            if (d.status === 'ok') {
                alert('Успіх: ' + d.message);
                bootstrap.Modal.getInstance(document.getElementById('resultModal')).hide();
            } else { alert('Помилка: ' + (d.error || 'Невідома')); }
        });
    }
});
