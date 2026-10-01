"""Стоимость запросов к DeepSeek в долларах — по официальным ценам deepseek-flash.

Цены сверены 2026-10-01: https://api-docs.deepseek.com/quick_start/pricing
"""
from datetime import datetime, timezone

# $ за 1 млн токенов: (вне пика, пик)
PRICES = {"hit": (0.003, 0.006), "miss": (0.15, 0.30), "out": (0.6, 1.2)}


def is_peak(t: datetime) -> bool:
    """Пик — будни 01:00–04:00 и 06:00–10:00 UTC (китайские праздники не учитываем)."""
    t = t.astimezone(timezone.utc)
    return t.weekday() < 5 and (1 <= t.hour < 4 or 6 <= t.hour < 10)


def cost_usd(usage: dict, when: datetime | None = None) -> float:
    i = 1 if is_peak(when or datetime.now(timezone.utc)) else 0
    hit = usage.get("prompt_cache_hit_tokens") or 0
    miss = usage.get("prompt_cache_miss_tokens")
    if miss is None:
        miss = (usage.get("prompt_tokens") or 0) - hit
    out = usage.get("completion_tokens") or 0  # размышления модели входят сюда же
    return (hit * PRICES["hit"][i] + miss * PRICES["miss"][i] + out * PRICES["out"][i]) / 1e6
