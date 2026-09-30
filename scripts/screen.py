"""Экран телефона на ПК через scrcpy; с --record ещё и запись в recordings/ для видео.

    python scripts/screen.py            # просто показать экран
    python scripts/screen.py --record   # показать и записать в recordings/<время>.mkv
"""
import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRCPY = ROOT / "tools" / "scrcpy" / "scrcpy.exe"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Экран телефона на ПК (scrcpy)")
    p.add_argument("--record", action="store_true", help="записать видео в recordings/")
    p.add_argument("--serial", help="серийный номер, если подключено несколько устройств")
    # На OxygenOS adb не может менять системные настройки, пока в «Для разработчиков» не включено
    # «Отключить мониторинг разрешений» — без этого scrcpy ругается на --show-touches и --stay-awake
    p.add_argument("--touches", action="store_true", help="показывать касания на экране (удобно для видео)")
    args = p.parse_args()

    exe = str(SCRCPY) if SCRCPY.exists() else shutil.which("scrcpy")
    if not exe:
        sys.exit("scrcpy не найден: ожидался в tools/scrcpy/")
    cmd = [exe, "--window-title=Lemonade Agent"]
    if args.touches:
        cmd.append("--show-touches")
    if args.serial:
        cmd.append(f"--serial={args.serial}")
    if args.record:
        # mkv не портится, если запись оборвалась; для публикации перегоним в mp4
        out = ROOT / "recordings" / f"{datetime.now():%Y%m%d-%H%M%S}.mkv"
        out.parent.mkdir(exist_ok=True)
        cmd.append(f"--record={out}")
        print(f"Запись идёт в {out}. Закрой окно scrcpy, чтобы остановить.")
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
