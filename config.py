import os
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
