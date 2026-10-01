"""Настройки из .env — без python-dotenv, чтобы на телефоне (Termux) не нужно было ставить лишних пакетов."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: str | Path = ROOT / ".env") -> None:
    """Читает строки KEY=VALUE в os.environ. Уже заданные переменные окружения не перезаписывает."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)
