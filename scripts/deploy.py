"""Залить агента на телефон (в Termux) и управлять ботом — всё с ПК.

    python scripts/deploy.py               # залить код и .env в ~/LemonadeAgent внутри Termux
    python scripts/deploy.py --start       # залить и (пере)запустить Telegram-бота на телефоне
    python scripts/deploy.py --autostart   # залить, запустить и включить автозапуск при загрузке (Magisk)
    python scripts/deploy.py --stop        # остановить бота
"""
import argparse
import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import termux  # noqa: E402

INCLUDE = ["agent", "interfaces", "bench", "phone", "tests", "requirements.txt", ".env"]
TAR = "/data/local/tmp/lemonade.tar"
SERVICE = "/data/adb/service.d/lemonade.sh"


def pack() -> bytes:
    buf = io.BytesIO()
    skip = lambda ti: None if "__pycache__" in ti.name or ti.name.endswith(".pyc") else ti  # noqa: E731
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in INCLUDE:
            if (ROOT / name).exists():
                tar.add(ROOT / name, arcname=name, filter=skip)
    return buf.getvalue()


def root(cmd: str):
    subprocess.run(["adb", "shell", f"su -c '{cmd}'"], check=True)


def deploy():
    data = pack()
    local = ROOT / "logs" / "_deploy.tar"
    local.parent.mkdir(exist_ok=True)
    local.write_bytes(data)
    try:
        subprocess.run(["adb", "push", str(local), TAR], check=True, capture_output=True)
        subprocess.run(["adb", "shell", f"chmod 644 {TAR}"], check=True)
        code = termux.run(f"mkdir -p ~/LemonadeAgent && tar -xf {TAR} -C ~/LemonadeAgent"
                          " && chmod 600 ~/LemonadeAgent/.env && echo \"код залит: $(du -sh ~/LemonadeAgent | cut -f1)\"")
    finally:
        local.unlink()
        subprocess.run(["adb", "shell", f"rm -f {TAR}"])  # в архиве .env — не оставляем его в общей папке
    if code:
        sys.exit(f"не удалось распаковать код на телефоне (код {code})")


def keep_awake():
    # бот должен слышать Telegram и с погасшим экраном
    root("echo lemonade > /sys/power/wake_lock; dumpsys deviceidle whitelist +com.termux > /dev/null")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Lemonade Agent: доставка на телефон")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--start", action="store_true")
    g.add_argument("--autostart", action="store_true")
    g.add_argument("--stop", action="store_true")
    args = p.parse_args()

    if args.stop:
        termux.run("pkill -f phone/run_bot.sh; pkill -f interfaces.telegram_bot; echo 'бот остановлен'")
        root(f"rm -f {SERVICE}; echo lemonade > /sys/power/wake_unlock")
        print("автозапуск выключен")
        return
    deploy()
    if args.autostart:
        subprocess.run(["adb", "push", str(ROOT / "phone" / "service.sh"), "/data/local/tmp/lemonade_service.sh"],
                       check=True, capture_output=True)
        root(f"mkdir -p /data/adb/service.d && cp /data/local/tmp/lemonade_service.sh {SERVICE}"
             f" && chmod 755 {SERVICE} && rm /data/local/tmp/lemonade_service.sh")
        print(f"автозапуск включён: {SERVICE}")
    if args.start or args.autostart:
        keep_awake()
        termux.run("bash ~/LemonadeAgent/phone/start_bot.sh")


if __name__ == "__main__":
    main()
