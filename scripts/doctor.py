"""Этап 0: проверка окружения — телефон по adb, прошивка, ключ DeepSeek, scrcpy.

    python scripts/doctor.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROPS = {
    "ro.product.model": "модель",
    "ro.product.device": "кодовое имя",
    "ro.build.display.id": "прошивка",
    "ro.build.version.release": "Android",
    "ro.build.version.security_patch": "патч безопасности",
    "ro.boot.flash.locked": "загрузчик заблокирован (1 = да)",
    "ro.boot.verifiedbootstate": "verified boot (green = заблокирован)",
    "sys.oem_unlock_allowed": "«Разблокировка OEM» включена (1 = да)",
}


def adb(*args: str) -> str:
    r = subprocess.run(["adb", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    return r.stdout.strip()


def check_phone() -> bool:
    print("== Телефон ==")
    lines = [line for line in adb("devices", "-l").splitlines()[1:] if line.strip()]
    if not lines:
        print("  телефон не виден: проверь кабель и «Отладку по USB», потом разреши доступ на экране телефона")
        return False
    for line in lines:
        print("  " + line)
    ready = [line.split()[0] for line in lines if line.split()[1] == "device"]
    if not ready:
        print("  → на экране телефона нажми «Разрешить» (лучше с галочкой «Всегда разрешать с этого компьютера»)")
        return False
    serial = ready[0]
    for prop, title in PROPS.items():
        print(f"  {title:<40} {adb('-s', serial, 'shell', 'getprop', prop) or '—'}")
    mem = adb("-s", serial, "shell", "grep MemTotal /proc/meminfo").split()
    if len(mem) >= 2:
        print(f"  {'оперативная память':<40} {int(mem[1]) / 1024 / 1024:.1f} ГБ")
    df = adb("-s", serial, "shell", "df -h /data").splitlines()
    if len(df) >= 2:
        size, used, avail = df[-1].split()[1:4]
        print(f"  {'память /data':<40} свободно {avail} из {size}")
    print(f"  {'экран':<40} {adb('-s', serial, 'shell', 'wm size').replace('Physical size: ', '')}")
    has_su = adb("-s", serial, "shell", "command -v su")
    print(f"  {'root (su)':<40} {'есть' if has_su else 'нет'}")
    return True


def check_deepseek() -> bool:
    print("== DeepSeek ==")
    try:
        from dotenv import load_dotenv
        from openai import OpenAI
    except ImportError:
        print("  нет пакетов: pip install -r requirements.txt")
        return False
    load_dotenv(ROOT / ".env")
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key or key.startswith("sk-your"):
        print("  ключ не найден: скопируй .env.example в .env и вставь свой ключ")
        return False
    client = OpenAI(api_key=key, base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    try:
        models = [m.id for m in client.models.list()]
    except Exception as e:  # сеть, неверный ключ, нет баланса — покажем как есть
        print(f"  запрос /models не прошёл: {type(e).__name__}: {e}")
        return False
    print("  ключ работает, модели: " + ", ".join(models))
    want = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    if want not in models:
        print(f"  ! модели {want} нет в списке — поправь DEEPSEEK_MODEL в .env")
    return True


def check_scrcpy() -> bool:
    print("== scrcpy ==")
    local = ROOT / "tools" / "scrcpy" / "scrcpy.exe"
    path = str(local) if local.exists() else shutil.which("scrcpy")
    print(f"  {path or 'не установлен (нужен для записи экрана в видео)'}")
    return bool(path)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    results = {"телефон": check_phone(), "DeepSeek": check_deepseek(), "scrcpy": check_scrcpy()}
    print("\nИтог: " + ", ".join(f"{k} {'OK' if ok else 'нет'}" for k, ok in results.items()))


if __name__ == "__main__":
    main()
