"""Память-навыки: удачные решения задач хранятся в SQLite и подсказываются агенту на похожих задачах.

Это самое простое «обучение на опыте»: веса модели не меняются, но агент получает в промпт свой прошлый удачный путь
и тратит меньше шагов на поиски. Насколько меньше — меряет бенчмарк (кривая обучения).
"""
import json
import re
import sqlite3
import time
from pathlib import Path


def _words(text: str) -> set[str]:
    # грубая «основа»: первые 5 букв, чтобы «будильник» и «будильника» совпадали; числа берём целиком
    return {w if w.isdigit() else w[:5] for w in re.findall(r"[a-zа-яё0-9]+", text.lower())
            if len(w) >= 3 or w.isdigit()}


def clean(steps: list[str]) -> list[str]:
    """Убирает из навыка то, что не переносится на следующий раз: нажатия в координаты (экран будет другим)
    и повторы — из нескольких вводов подряд остаётся последний. Иначе в память попадал «грязный» путь
    первой удачной попытки, и подсказка вела агента обратно в ту же яму (так было с браузером)."""
    out: list[str] = []
    for s in steps:
        if "в точку" in s:
            continue
        if out and (s == out[-1] or (s.startswith("type ") and out[-1].startswith("type "))):
            out[-1] = s
            continue
        out.append(s)
    return out


def similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


class Memory:
    def __init__(self, path: str | Path, threshold: float = 0.4, k: int = 2):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS skills "
                        "(task TEXT PRIMARY KEY, steps TEXT, n_steps INTEGER, created REAL, uses INTEGER DEFAULT 0)")
        self.threshold, self.k = threshold, k

    def save(self, task: str, steps: list[str]) -> bool:
        """Сохраняет путь, если для этой задачи его ещё нет или новый короче. Пустой путь не сохраняем."""
        steps = clean(steps)
        if not steps:
            return False
        row = self.db.execute("SELECT n_steps FROM skills WHERE task = ?", (task,)).fetchone()
        if row and row[0] <= len(steps):
            return False
        self.db.execute("INSERT OR REPLACE INTO skills (task, steps, n_steps, created) VALUES (?, ?, ?, ?)",
                        (task, json.dumps(steps, ensure_ascii=False), len(steps), time.time()))
        self.db.commit()
        return True

    def recall(self, task: str) -> list[tuple[str, list[str]]]:
        rows = self.db.execute("SELECT task, steps FROM skills").fetchall()
        scored = sorted(((similarity(task, t), t, s) for t, s in rows), key=lambda x: x[0], reverse=True)
        found = [(t, json.loads(s)) for score, t, s in scored[:self.k] if score >= self.threshold]
        for t, _ in found:
            self.db.execute("UPDATE skills SET uses = uses + 1 WHERE task = ?", (t,))
        self.db.commit()
        return found

    def exact(self, task: str) -> list[str] | None:
        """Навык для той же самой задачи (тот же текст) — его можно повторить без модели."""
        row = self.db.execute("SELECT steps FROM skills WHERE task = ?", (task,)).fetchone()
        return json.loads(row[0]) if row else None

    def hint(self, task: str) -> str | None:
        """Текст для промпта или None, если похожего опыта нет."""
        skills = self.recall(task)
        if not skills:
            return None
        lines = ["Похожие задачи, которые ты уже решал успешно. Используй как подсказку, но сверяйся с экраном: "
                 "номера элементов могли измениться, а задача может отличаться."]
        lines += [f"— «{t}»: " + " → ".join(steps) for t, steps in skills]
        return "\n".join(lines)

    def __len__(self):
        return self.db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]

    def __bool__(self):
        # без этого пустая память (len == 0) была бы «ложной», и `if memory:` её пропускал —
        # так и вышло в первом запуске бенчмарка: агент не учился вовсе
        return True
