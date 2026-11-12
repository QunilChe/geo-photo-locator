import subprocess
import os
import logging
from config import Config

logger = logging.getLogger(__name__)

def run_deep_scripts(image_path, filename, lat, lon):
    """
    Запускає безпечні скрипти geo-sleuth (Google Street View), 
    які не потребують складних OSM-даних.
    """
    results = {}
    out_base = os.path.join(Config.BASE_DIR, 'analysis', f'{filename}_deep')
    
    if not lat or not lon:
        results['gsv'] = {'success': False, 'error': 'Немає координат для пошуку панорами'}
        return results

    # Запускаємо gsv.py для пошуку панорами Google Street View
    # Формат: gsv.py find --lat <lat> --lon <lon> --out-dir <dir>
    gsv_out = os.path.join(out_base, 'gsv')
    cmd_gsv = ['uv', 'run', os.path.join(Config.GEO_SLEUTH_PATH, 'gsv.py'), 
               'find', '--lat', str(lat), '--lon', str(lon), '--out-dir', gsv_out]
    
    try:
        r_gsv = subprocess.run(cmd_gsv, capture_output=True, text=True, timeout=120)
        results['gsv'] = {'success': r_gsv.returncode == 0, 'stdout': r_gsv.stdout, 'stderr': r_gsv.stderr}
    except Exception as e:
        results['gsv'] = {'success': False, 'error': str(e)}

    return results
