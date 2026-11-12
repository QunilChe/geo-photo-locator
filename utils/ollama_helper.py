import logging
import json
import os
import ollama
import concurrent.futures
import io
from PIL import Image
from pydantic import BaseModel
from typing import List
from config import Config

logger = logging.getLogger(__name__)

class LocationOption(BaseModel):
    name: str
    lat: float
    lon: float
    reasoning: str
    confidence: float

class AIResponse(BaseModel):
    suggestions: List[LocationOption]

def get_knowledge_base():
    kb_path = os.path.join(Config.BASE_DIR, 'knowledge_base.json')
    if os.path.exists(kb_path):
        with open(kb_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_to_knowledge_base(location_name, lat, lon):
    kb_path = os.path.join(Config.BASE_DIR, 'knowledge_base.json')
    kb = get_knowledge_base()
    if not any(item['name'] == location_name for item in kb):
        kb.append({"name": location_name, "lat": lat, "lon": lon})
        with open(kb_path, 'w', encoding='utf-8') as f:
            json.dump(kb, f, ensure_ascii=False, indent=2)

def resize_image_for_ai(image_path, max_size=512):
    try:
        with Image.open(image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.thumbnail((max_size, max_size))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue()
    except Exception as e:
        logger.warning(f"Не вдалося зменшити фото: {e}. Використовуємо оригінал.")
        with open(image_path, "rb") as f:
            return f.read()

def get_plate_region_hint(report_text):
    """Шукає коди регіонів України в тексті і повертає підказку для ШІ"""
    text_lower = report_text.lower()
    
    # Розширений довідник (старі та нові коди)
    plate_map = {
        'aa': 'Київ', 'ka': 'Київ', 'tt': 'Київ', 'ta': 'Київ',
        'ai': 'Київська область', 'ki': 'Київська область', 'ti': 'Київська область', 'me': 'Київська область',
        'bc': 'Львівська область', 'hc': 'Львівська область', 'cc': 'Львівська область', 'ec': 'Львівська область',
        'ac': 'Волинська область', 'kc': 'Волинська область', 'cm': 'Волинська область', 'tc': 'Волинська область',
        'ae': 'Дніпропетровська область', 'ke': 'Дніпропетровська область', 'pp': 'Дніпропетровська область', 'mi': 'Дніпропетровська область',
        'ax': 'Харківська область', 'kx': 'Харківська область', 'xx': 'Харківська область', 'ex': 'Харківська область',
        'bh': 'Одеська область', 'hh': 'Одеська область', 'oo': 'Одеська область', 'eh': 'Одеська область',
        'bi': 'Полтавська область', 'hi': 'Полтавська область', 'xi': 'Полтавська область', 'ei': 'Полтавська область',
        'bo': 'Тернопільська область', 'ho': 'Тернопільська область', 'xo': 'Тернопільська область', 'eo': 'Тернопільська область',
        'at': 'Івано-Франківська область', 'kt': 'Івано-Франківська область', 'to': 'Івано-Франківська область', 'xc': 'Івано-Франківська область',
        'am': 'Житомирська область', 'km': 'Житомирська область', 'tm': 'Житомирська область', 'mb': 'Житомирська область',
        'ao': 'Закарпатська область', 'ko': 'Закарпатська область', 'mt': 'Закарпатська область', 'mo': 'Закарпатська область',
        'ap': 'Запорізька область', 'kp': 'Запорізька область', 'tp': 'Запорізька область', 'mp': 'Запорізька область',
        'ba': 'Кіровоградська область', 'ha': 'Кіровоградська область', 'xa': 'Кіровоградська область', 'ea': 'Кіровоградська область',
        'bb': 'Луганська область', 'hb': 'Луганська область', 'ee': 'Луганська область', 'eb': 'Луганська область',
        'be': 'Миколаївська область', 'he': 'Миколаївська область', 'xe': 'Миколаївська область', 'xh': 'Миколаївська область',
        'bk': 'Рівненська область', 'hk': 'Рівненська область', 'xk': 'Рівненська область', 'ek': 'Рівненська область',
        'bm': 'Сумська область', 'hm': 'Сумська область', 'xm': 'Сумська область', 'em': 'Сумська область',
        'bt': 'Херсонська область', 'ht': 'Херсонська область', 'xt': 'Херсонська область', 'et': 'Херсонська область',
        'bx': 'Хмельницька область', 'hx': 'Хмельницька область', 'ox': 'Хмельницька область', 'px': 'Хмельницька область',
        'ca': 'Черкаська область', 'ia': 'Черкаська область', 'oa': 'Черкаська область', 'pa': 'Черкаська область',
        'cb': 'Чернігівська область', 'ib': 'Чернігівська область', 'ob': 'Чернігівська область', 'pb': 'Чернігівська область',
        'ce': 'Чернівецька область', 'ie': 'Чернівецька область', 'oe': 'Чернівецька область', 'pe': 'Чернівецька область',
        'ak': 'АР Крим', 'ma': 'АР Крим', 'tk': 'АР Крим', 'mk': 'АР Крим',
        'ch': 'Севастополь', 'ih': 'Севастополь', 'oh': 'Севастополь', 'ph': 'Севастополь'
    }
    
    hints = []
    for code, region in plate_map.items():
        if f' {code}' in text_lower or f'[{code}' in text_lower or f'"{code}' in text_lower:
            hints.append(f"Код номерного знаку '{code.upper()}' вказує на {region}.")
    
    if hints:
        return "УВАГА! Знайдено підказки по номерах: " + " ".join(hints) + " Врахуй це, але пам'ятай, що з 2023 року регіональна прив'язка не є обов'язковою."
    
    return ""

def analyze_clues_with_ollama(image_path: str, report_text: str):
    kb = get_knowledge_base()
    kb_text = "\n".join([f"- {item['name']}" for item in kb])

    plate_hint = get_plate_region_hint(report_text)
    
    # Збільшуємо кількість вхідних даних (беремо більше тексту)
    short_report = report_text[:4000]

    prompt = f"""
    You are an OSINT analyst. Look at the image carefully.
    
    {plate_hint}
    
    CLUES FROM OCR AND SEARCH:
    {short_report}
    
    PREVIOUS LOCATIONS:
    {kb_text}
    
    Return top 3 locations as JSON with key 'suggestions'. Each suggestion must have name, lat, lon, reasoning, confidence.
    """

    try:
        image_bytes = resize_image_for_ai(image_path)
        logger.info("Відправляємо фото в Ollama (очікуємо до 10 хвилин)...")
            
        def call_ollama():
            return ollama.chat(
                model=Config.OLLAMA_MODEL,
                messages=[{'role': 'user', 'content': prompt, 'images': [image_bytes]}],
                format=AIResponse.model_json_schema(),
                options={
                    'temperature': 0.1, 
                    'num_ctx': 8192, # ЗБІЛЬШУЄМО КОНТЕКСТ ДО 8192
                } 
            )

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(call_ollama)
            try:
                response = future.result(timeout=600)
            except concurrent.futures.TimeoutError:
                raise Exception("Модель занадто довго думає (тайм-аут 10 хвилин).")

        content = response['message']['content'].strip()
        clean_text = content.replace('```json', '').replace('```', '').strip()
        
        start = clean_text.find('{')
        end = clean_text.rfind('}')
        if start != -1 and end != -1:
            clean_text = clean_text[start:end+1]

        ai_result = AIResponse.model_validate_json(clean_text)
        
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="geo_photo_locator_ai")
        for sug in ai_result.suggestions:
            if not sug.lat or not sug.lon:
                loc = geolocator.geocode(sug.name)
                if loc: sug.lat, sug.lon = loc.latitude, loc.longitude
                
        ai_result.suggestions = [s for s in ai_result.suggestions if s.lat and s.lon]
        if ai_result.suggestions: 
            return ai_result
            
    except Exception as e:
        logger.error(f"Ollama failed: {e}")

    fallback = [
        LocationOption(name="Львів", lat=49.8397, lon=24.0297, reasoning="Базовий варіант (ШІ не впорався)", confidence=0.3)
    ]
    return AIResponse(suggestions=fallback)
