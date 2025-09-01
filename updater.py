import os
import zipfile
import shutil

APP_DIR = "app"
PATCH_FILE = os.path.join("update", "patch.zip")

def apply_patch():
    if not os.path.exists(PATCH_FILE):
        print("❌ Файл patch.zip не найден.")
        return

    print("📦 Распаковка патча...")
    with zipfile.ZipFile(PATCH_FILE, 'r') as zip_ref:
        zip_ref.extractall(APP_DIR)

    print("✅ Патч применён успешно.")
    os.remove(PATCH_FILE)

if __name__ == "__main__":
    apply_patch()
