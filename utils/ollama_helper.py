import logging
import json
import os
import re
from pydantic import BaseModel
from typing import List, Optional
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

def extract_entities_from_text(text: str):
    """Шукає конкретні міста в тексті звіту та повертає їх з координатами"""
    found = {}
    text_lower = text.lower()
    
    # Жорстко прописані міста (для миттєвого результату)
    city_map = {
        'lutsk': ('Луцьк', 50.7472, 25.3254), 'луцьк': ('Луцьк', 50.7472, 25.3254),
        'lviv': ('Львів', 49.8397, 24.0297), 'львів': ('Львів', 49.8397, 24.0297), 'львов': ('Львів', 49.8397, 24.0297),
        'navaria': ('Наварія', 49.7546, 23.9498), 'наварія': ('Наварія', 49.7546, 23.9498),
        'kyiv': ('Київ', 50.4501, 30.5234), 'київ': ('Київ', 50.4501, 30.5234), 'capital city of ukraine': ('Київ', 50.4501, 30.5234),
        'dnipro': ('Дніпро', 48.4647, 35.0462), 'дніпро': ('Дніпро', 48.4647, 35.0462), 'dp.ua': ('Дніпро', 48.4647, 35.0462),
        'kharkiv': ('Харків', 49.9935, 36.2304), 'харків': ('Харків', 49.9935, 36.2304),
        'belgrade': ('Белград', 44.7866, 20.4489), 'zemun': ('Белград (Земун)', 44.8450, 20.4010),
        'ülemiste': ('Таллінн (Юлемісте)', 59.4220, 24.8000), 'tallinn': ('Таллінн', 59.4370, 24.7536),
        'wlodawa': ('Влодава, Польща', 51.5500, 23.5500),
        'rostov': ('Ростов-на-Дону', 47.2357, 39.7015),
        'ulyanovsk': ('Ульяновськ', 54.3142, 48.4031),
        'bryansk': ('Брянськ', 53.2434, 34.3634),
        'taganrog': ('Таганрог', 47.2095, 38.9351)
    }
    
    for key, (name, lat, lon) in city_map.items():
        if key in text_lower:
            if name not in found:
                found[name] = {"lat": lat, "lon": lon, "reason": "Знайдено в тексті звіту"}
                
    return found

def analyze_clues_with_ollama(image_path: str, report_text: str):
    extracted_places = extract_entities_from_text(report_text)
    kb = get_knowledge_base()
    
    # Формуємо список кандидатів
    candidates = []
    for name, data in extracted_places.items():
        candidates.append(f"- {name} (Причина: {data['reason']})")
        
    for item in kb:
        if item['name'] not in extracted_places:
            candidates.append(f"- {item['name']} (З вашої бази знань)")
            
    if not candidates:
        candidates = ["- Львів (Базовий варіант)", "- Наварія (Базовий варіант)"]

    candidates_str = "\n".join(candidates)
    
    try:
        from ollama import chat
        
        prompt = f"""
        You are an OSINT expert. User is from Lviv, but this photo might be from somewhere else.
        I have extracted these locations from the search report and user's history:
        
        {candidates_str}
        
        Look at the image. It shows a railway, city buildings. The EXIF says +02:00.
        If you see "Kyiv" or "Dnipro" in the candidates, prioritize them over the user's default "Lviv", because the search engine found specific matches.
        
        Choose the top 3 most likely locations from the list above. Return a JSON object with 'suggestions'.
        """

        response = chat(
            model=Config.OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': prompt, 'images': [image_path]}],
            format=AIResponse.model_json_schema(),
            options={'temperature': 0.1}
        )
        
        ai_result = AIResponse.model_validate_json(response.message.content)
        
        # Якщо ШІ повернув порожній список, беремо те, що знайшов Python
        if not ai_result.suggestions:
            raise ValueError("Empty AI response")
            
        # Додаємо координати, якщо ШІ їх не вказав
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="geo_photo_locator_ai")
        
        for sug in ai_result.suggestions:
            if not sug.lat or not sug.lon:
                if sug.name in extracted_places:
                    sug.lat = extracted_places[sug.name]['lat']
                    sug.lon = extracted_places[sug.name]['lon']
                else:
                    loc = geolocator.geocode(sug.name)
                    if loc:
                        sug.lat = loc.latitude
                        sug.lon = loc.longitude
                        
        ai_result.suggestions = [s for s in ai_result.suggestions if s.lat and s.lon]
        
        if ai_result.suggestions:
            return ai_result

    except Exception as e:
        logger.warning(f"Ollama analysis failed: {e}")

    # FALLBACK: Якщо ШІ впав, просто беремо те, що знайшов Python (або базу)
    fallback = []
    for name, data in extracted_places.items():
        fallback.append(LocationOption(name=name, lat=data['lat'], lon=data['lon'], reasoning=data['reason'], confidence=0.8))
        
    if not fallback:
        for item in kb[:3]:
            fallback.append(LocationOption(name=item['name'], lat=item['lat'], lon=item['lon'], reasoning="База знань", confidence=0.3))
            
    if not fallback:
        fallback = [
            LocationOption(name="Львів", lat=49.8397, lon=24.0297, reasoning="Базовий варіант", confidence=0.1),
            LocationOption(name="Наварія", lat=49.7546, lon=23.9498, reasoning="Базовий варіант", confidence=0.1)
        ]
        
    return AIResponse(suggestions=fallback[:3])
