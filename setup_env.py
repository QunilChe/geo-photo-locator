import os
import urllib.request
import zipfile
import io
import shutil

base_dir = os.path.dirname(os.path.abspath(__file__))
geo_sleuth_dir = os.path.join(base_dir, "geo-sleuth")
target_intake = os.path.join(geo_sleuth_dir, "skills", "geo-sleuth", "scripts", "intake.py")

if not os.path.exists(target_intake):
    print("⏳ Завантаження geo-sleuth з GitHub (це може зайняти хвилину)...")
    url = "https://github.com/Oldcircle/geo-sleuth/archive/refs/heads/main.zip"
    try:
        with urllib.request.urlopen(url) as response:
            zip_data = response.read()
        
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            z.extractall(base_dir)
            
        extracted_folder = os.path.join(base_dir, "geo-sleuth-main")
        if os.path.exists(extracted_folder):
            if os.path.exists(geo_sleuth_dir):
                shutil.rmtree(geo_sleuth_dir)
            os.rename(extracted_folder, geo_sleuth_dir)
            
        print("✅ geo-sleuth успішно завантажено!")
    except Exception as e:
        print(f"❌ Помилка завантаження: {e}")
        print("Перевірте інтернет-з'єднання.")
else:
    print("✅ geo-sleuth вже на місці.")