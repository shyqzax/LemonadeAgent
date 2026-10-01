"""«Сторож»: ждёт, пока на телефоне закончится бенчмарк, и присылает владельцу итоги в Telegram.

    python -m bench.notify memory baseline      # имена прогонов — их таблицы попадут в сообщение
"""
import os
import subprocess
import sys
import time

from agent.config import ROOT, load_env
from interfaces.telegram_bot import Telegram, TelegramError


def bench_running() -> bool:
    return subprocess.run(["pgrep", "-f", "bench.run_bench"], capture_output=True).returncode == 0


def report(names: list[str]) -> str:
    parts = ["🏁 Бенчмарк закончился"]
    for name in names:
        summary = ROOT / "logs" / "bench" / name / "summary.md"
        table = summary.read_text("utf-8").split("\n", 2)[-1].strip() if summary.exists() else "нет результатов"
        parts.append(f"\n«{name}»\n{table}")
    return "\n".join(parts)


def main():
    load_env()
    names = sys.argv[1:]
    while bench_running():
        time.sleep(60)
    tg, owner = Telegram(os.environ["TELEGRAM_BOT_TOKEN"]), int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
    for attempt in range(10):  # сеть могла моргнуть — пробуем ещё
        try:
            tg.call("sendMessage", chat_id=owner, text=report(names)[:4000])
            return
        except TelegramError:
            time.sleep(60)


if __name__ == "__main__":
    main()
