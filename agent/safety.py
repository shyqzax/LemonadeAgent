"""Безопасность: опасные нажатия подтверждает человек; приложения из чёрного списка агенту недоступны."""
import re

# Подписи кнопок, нажатие на которые может что-то отправить, оплатить или удалить
DANGER = re.compile(r"отправ|\bsend|оплат|\bpay|купи|\bbuy|purchase|оформ|checkout|удал|delete|стере|erase|"
                    r"сброс|reset|перевест|перевод|transfer|подписат|subscribe", re.I)

# Части имён пакетов, куда агенту нельзя: банки, кошельки, криптобиржи
BLOCKED_APPS = ("bank", "sber", "tinkoff", "tbank", "vtb", "alfabank", "wallet", "spay", "paypal",
                "revolut", "binance", "crypto")


def needs_confirmation(action: str, element) -> str | None:
    """Причина спросить человека или None, если действие безопасно."""
    if element is not None and DANGER.search(element.label):
        return f"{action} «{element.label}»"
    return None


def is_blocked_app(name: str) -> bool:
    name = name.lower()
    return any(b in name for b in BLOCKED_APPS)
