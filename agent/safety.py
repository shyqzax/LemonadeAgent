"""Безопасность: опасные нажатия подтверждает человек; приложения из чёрного списка агенту недоступны."""
import re

# Подписи кнопок, нажатие на которые может что-то отправить, оплатить или удалить
DANGER = re.compile(r"отправ|\bsend|оплат|\bpay|купи|\bbuy|purchase|оформ|checkout|удал|delete|стере|erase|"
                    r"сброс|reset|перевест|перевод|transfer|подписат|subscribe", re.I)
# ...кроме безобидных случаев: «Удалить запрос» в поиске — это просто очистка строки, а не удаление данных
HARMLESS = re.compile(r"запрос|query|поиск|search|очист|clear", re.I)

# Части имён пакетов, куда агенту нельзя: банки, кошельки, криптобиржи
BLOCKED_APPS = ("bank", "sber", "tinkoff", "tbank", "vtb", "alfabank", "wallet", "spay", "paypal",
                "revolut", "binance", "crypto")


def needs_confirmation(action: str, element, package: str = "") -> str | None:
    """Причина спросить человека или None, если действие безопасно."""
    label = element.label if element is not None else ""
    # системное окно «Разрешить приложению доступ к…»: агент однажды сам выдал Часам уведомления — больше не выдаёт
    if "permissioncontroller" in package:
        return f"выдать или отклонить разрешение: «{label or 'нажатие в окне разрешений'}»"
    if label and DANGER.search(label) and not HARMLESS.search(label):
        return f"{action} «{label}»"
    return None


def is_blocked_app(name: str) -> bool:
    name = name.lower()
    return any(b in name for b in BLOCKED_APPS)
