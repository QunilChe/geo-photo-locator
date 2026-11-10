import subprocess, os, logging
from config import Config

logger = logging.getLogger(__name__)

def run_script(script_name, args, timeout=None):
    script_path = os.path.join(Config.GEO_SLEUTH_PATH, script_name)
    
    if not os.path.exists(script_path):
        return {'success': False, 'error': f'Скрипт {script_name} не знайдено', 'stdout': '', 'stderr': ''}
        
    cmd = ['uv', 'run', script_path] + args
    logger.info('Run: ' + ' '.join(cmd))
    
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout or Config.GEO_SLEUTH_TIMEOUT, check=False)
        
        # Головна перевірка: якщо код повернення 0, то все добре, навіть якщо stderr не порожній
        is_success = (r.returncode == 0)
        
        return {
            'success': is_success, 
            'returncode': r.returncode,
            'stdout': r.stdout, 
            'stderr': r.stderr
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Таймаут', 'stdout': '', 'stderr': ''}
    except Exception as e:
        return {'success': False, 'error': str(e), 'stdout': '', 'stderr': ''}

def analyze_photo(image_path, filename):
    results = {}
    out_base = os.path.join(Config.BASE_DIR, 'analysis', filename)
    
    results['intake'] = run_script('intake.py', [image_path, '--out-dir', out_base + '_intake'])
    results['sat_scan'] = run_script('sat_scan.py', [image_path, '--out-dir', out_base + '_sat'])
    results['terrain'] = run_script('terrain.py', ['scan', '--image', image_path, '--out-dir', out_base + '_terrain'])
    
    return results
