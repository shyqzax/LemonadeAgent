"""Запуск агента из командной строки.

    python -m interfaces.cli "включи тёмную тему"
    python -m interfaces.cli "set an alarm for 7:00" --mode tree --max-steps 15

Остановить агента в любой момент: Ctrl+C.
"""
import argparse
import sys

from agent.brain import Brain
from agent.config import load_env
from agent.device import AdbDevice, RootDevice
from agent.loop import MODES, Agent


def confirm(reason: str) -> bool:
    try:
        return input(f"   ! Агент хочет: {reason}. Разрешить? [y/N] ").strip().lower() in ("y", "yes", "д", "да")
    except EOFError:  # запуск без консоли: подтвердить некому — значит нельзя
        print("нет")
        return False


def ask(question: str) -> str:
    try:
        return input(f"   ? {question}\n   > ")
    except EOFError:
        return "пользователь недоступен"


def print_step(r: dict):
    a = r["action"]
    short = {k: v for k, v in a.items() if k != "thought"}
    print(f"[{r['step']:>2}] {r['package']} | {a.get('thought', '')}")
    print(f"     {short} → {r['outcome']}  ({r['seconds']} с)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    p = argparse.ArgumentParser(description="Lemonade Agent: ИИ управляет Android-телефоном")
    p.add_argument("task", help="что сделать на телефоне")
    p.add_argument("--mode", choices=MODES, default="both", help="что видит мозг (по умолчанию both)")
    p.add_argument("--max-steps", type=int, default=25)
    p.add_argument("--serial", help="серийный номер, если подключено несколько устройств")
    p.add_argument("--root", action="store_true", help="запуск прямо на телефоне (Termux + su)")
    args = p.parse_args()

    device = RootDevice() if args.root else AdbDevice(args.serial)
    agent = Agent(device, Brain(), mode=args.mode, max_steps=args.max_steps, confirm=confirm,
                  ask=ask, on_step=print_step)
    print(f"Задача: {args.task}  (режим {args.mode}, до {args.max_steps} шагов)\n")
    try:
        r = agent.run(args.task)
    except KeyboardInterrupt:
        print("\n■ Остановлено (Ctrl+C)")
        sys.exit(130)
    mark = "✔ Готово" if r["success"] else "✘ Не вышло"
    print(f"\n{mark}: {r['summary']}")
    print(f"   шагов {r['steps']}, {r['seconds']} с, токенов {r['prompt_tokens']} + {r['completion_tokens']}")
    print(f"   лог: {r['log_dir']}")


if __name__ == "__main__":
    main()
