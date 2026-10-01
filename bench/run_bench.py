"""Бенчмарк: прогон задач с автопроверкой, раундами — чтобы увидеть, как агент учится на своём опыте.

    python -m bench.run_bench --root --rounds 3 --memory --name memory      # на телефоне, с памятью
    python -m bench.run_bench --root --rounds 1 --name baseline             # без памяти — точка отсчёта
    python -m bench.run_bench --only dark_on,bt_on --rounds 1               # с ПК по adb, пара задач

Результаты: logs/bench/<имя>/results.jsonl (строка на задачу) и summary.md (таблица по раундам).
Подтверждений во время бенчмарка никто не даёт: опасное запрещено, как и без человека.
"""
import argparse
import json
import sys
import time
from datetime import datetime

from agent.brain import Brain
from agent.config import ROOT, load_env
from agent.device import AdbDevice, DeviceError, RootDevice
from agent.loop import MODES, Agent
from agent.memory import Memory
from bench.tasks import RESTORE_KEYS, TASKS

APPS = ["com.android.settings", "com.android.calculator2", "com.android.contacts", "com.android.deskclock",
        "org.lineageos.jelly", "com.android.vending"]


def reset(device, task):
    """Одинаковый старт: закрыть приложения, домашний экран, подготовить состояние под задачу."""
    device.shell("; ".join(f"am force-stop {p}" for p in APPS))
    for cmd in task.setup:
        device.shell(cmd, timeout=30)
    device.wake()
    device.key(3)
    time.sleep(1.5)


def summarize(rows: list[dict]) -> str:
    lines = ["| Раунд | Успех | Шагов | Вызовов модели | Время | Стоимость раунда | Повтор навыка |",
             "|---|---|---|---|---|---|---|"]
    for rnd in sorted({r["round"] for r in rows}):
        rs = [r for r in rows if r["round"] == rnd]
        ok = sum(r["success"] for r in rs)
        avg = lambda k: sum(r.get(k, 0) for r in rs) / len(rs)  # noqa: E731
        lines.append(f"| {rnd} | {ok}/{len(rs)} ({100 * ok / len(rs):.0f}%) | {avg('steps'):.1f} | {avg('llm_calls'):.1f} "
                     f"| {avg('seconds'):.0f} с | ${sum(r['cost_usd'] for r in rs):.3f} "
                     f"| {sum(1 for r in rs if r.get('replayed'))} |")
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    load_env()
    p = argparse.ArgumentParser(description="Lemonade Agent: бенчмарк")
    p.add_argument("--root", action="store_true", help="на телефоне через su (иначе — с ПК по adb)")
    p.add_argument("--rounds", type=int, default=1)
    p.add_argument("--memory", action="store_true", help="включить память-навыки (учится между раундами)")
    p.add_argument("--only", help="id задач через запятую")
    p.add_argument("--mode", choices=MODES, default="both")
    p.add_argument("--max-steps", type=int, default=20)
    p.add_argument("--name", default=datetime.now().strftime("%Y%m%d-%H%M"))
    args = p.parse_args()

    tasks = [t for t in TASKS if not args.only or t.id in args.only.split(",")]
    out = ROOT / "logs" / "bench" / args.name
    out.mkdir(parents=True, exist_ok=True)
    device = RootDevice() if args.root else AdbDevice()
    memory = Memory(out / "memory.db") if args.memory else None
    agent = Agent(device, Brain(), mode=args.mode, max_steps=args.max_steps, log_root=str(out / "runs"),
                  memory=memory, autosave=False)
    saved = {(ns, k): device.shell(f"settings get {ns} {k}").strip() for ns, k in RESTORE_KEYS}
    rows = []
    print(f"Бенчмарк «{args.name}»: {len(tasks)} задач × {args.rounds} раундов, "
          f"память {'вкл' if memory is not None else 'выкл'}")
    try:
        with open(out / "results.jsonl", "a", encoding="utf-8") as f:
            for rnd in range(1, args.rounds + 1):
                for t in tasks:
                    try:
                        reset(device, t)
                        r = agent.run(t.text)
                    except DeviceError as e:
                        r = {"steps": 0, "seconds": 0, "cost_usd": 0, "memory_hint": False, "llm_calls": 0,
                             "replayed": 0, "success": False, "summary": f"сбой: {e}", "skill": []}
                    try:
                        ok = bool(t.check(device, r["summary"]))
                    except Exception as e:  # проверка не смогла прочитать состояние — считаем провалом
                        print(f"   проверка {t.id} упала: {e}")
                        ok = False
                    learned = bool(memory is not None and ok and memory.save(t.text, r.get("skill", [])))
                    row = {"round": rnd, "id": t.id, "level": t.level, "success": ok, "claimed": r["success"],
                           "steps": r["steps"], "llm_calls": r["llm_calls"], "replayed": r["replayed"],
                           "seconds": r["seconds"], "cost_usd": r["cost_usd"],
                           "memory_hint": r["memory_hint"], "learned": learned, "summary": r["summary"],
                           "time": datetime.now().isoformat(timespec="seconds")}
                    rows.append(row)
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    mark = "✔" if ok else ("✘ (агент считал, что справился)" if r["success"] else "✘")
                    hint = " 💡" if r["memory_hint"] else ""
                    replay = f" 🔁{r['replayed']}" if r["replayed"] else ""
                    print(f"[р{rnd}] {t.id:16} {mark} {r['steps']:>2} ш {r['llm_calls']:>2} выз {r['seconds']:>5.0f} с "
                          f"${r['cost_usd']:.4f}{hint}{replay}")
    finally:
        for (ns, k), v in saved.items():
            if v != "null":
                device.shell(f"settings put {ns} {k} {v}")
        if rows:
            table = summarize(rows)
            (out / "summary.md").write_text(f"# Бенчмарк «{args.name}»\n\n{table}\n", encoding="utf-8")
            print("\n" + table)


if __name__ == "__main__":
    main()
