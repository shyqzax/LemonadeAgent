"""Задачи бенчмарка.

У каждой задачи: текст, подготовка телефона (чтобы старт всегда был одинаковым) и автопроверка —
по состоянию телефона, а не по словам агента. Для задач-вопросов проверяем ответ агента.

Задачи, которые рвут связь (Wi-Fi, режим полёта, VPN), не берём: агент живёт в телефоне и потерял бы сеть.
"""
import re
from dataclasses import dataclass
from typing import Callable

CONTACT = "Лимон Тестов"
CHAIN_CONTACT = "Android 16"


@dataclass
class Task:
    id: str
    text: str
    level: str               # easy / medium / hard
    setup: list[str]         # shell-команды перед задачей
    check: Callable          # (device, ответ агента) -> bool


def setting(ns: str, key: str, ok: Callable[[str], bool]) -> Callable:
    return lambda d, a: ok(d.shell(f"settings get {ns} {key}").strip())


def answer_has(*variants: str) -> Callable:
    return lambda d, a: any(v.lower() in a.lower().replace(" ", " ") for v in variants)


def night(expected: str) -> Callable:
    return lambda d, a: f"Night mode: {expected}" in d.shell("cmd uimode night")


def alarm_at(hhmm: str) -> Callable:
    # «Next alarm clock information:» в dumpsys alarm показывает ближайший будильник с датой и временем
    def check(d, a):
        out = d.shell("dumpsys alarm")
        i = out.find("Next alarm clock information")
        return i >= 0 and f" {hhmm}:00" in out[i:i + 400]
    return check


def contact_exists(name: str) -> Callable:
    return lambda d, a: name in d.shell(
        "content query --uri content://com.android.contacts/raw_contacts --projection display_name --where deleted=0")


def battery_in_answer(d, a) -> bool:
    level = int(re.search(r"level: (\d+)", d.shell("dumpsys battery")).group(1))
    return any(str(v) in a for v in (level - 1, level, level + 1))


def on_screen(*texts: str) -> Callable:
    def check(d, a):
        xml = d.ui_xml()
        return any(t in xml for t in texts)
    return check


def delete_contact(name: str) -> str:
    return (f"content delete --uri 'content://com.android.contacts/raw_contacts?caller_is_syncadapter=true' "
            f"--where \"display_name='{name}'\"")


S = "settings put"
CLOCK_RESET = ["pm clear com.android.deskclock", "pm grant com.android.deskclock android.permission.POST_NOTIFICATIONS"]

TASKS = [
    # --- настройки: включить / выключить ---
    Task("dark_on", "Включи тёмную тему", "easy", ["cmd uimode night no"], night("yes")),
    Task("dark_off", "Выключи тёмную тему", "easy", ["cmd uimode night yes"], night("no")),
    Task("bt_on", "Включи Bluetooth", "easy", ["cmd bluetooth_manager disable", "sleep 2"],
         setting("global", "bluetooth_on", lambda v: v == "1")),
    Task("bt_off", "Выключи Bluetooth", "easy", ["cmd bluetooth_manager enable", "sleep 2"],
         setting("global", "bluetooth_on", lambda v: v == "0")),
    Task("dnd_on", "Включи режим «Не беспокоить»", "easy", ["cmd notification set_dnd off"],
         setting("global", "zen_mode", lambda v: v not in ("0", "null"))),
    Task("dnd_off", "Выключи режим «Не беспокоить»", "easy", ["cmd notification set_dnd on"],
         setting("global", "zen_mode", lambda v: v == "0")),
    Task("rotate_off", "Отключи автоповорот экрана", "easy", [f"{S} system accelerometer_rotation 1"],
         setting("system", "accelerometer_rotation", lambda v: v == "0")),
    Task("rotate_on", "Включи автоповорот экрана", "easy", [f"{S} system accelerometer_rotation 0"],
         setting("system", "accelerometer_rotation", lambda v: v == "1")),
    Task("location_on", "Включи геолокацию", "easy", ["cmd location set-location-enabled false"],
         lambda d, a: "true" in d.shell("cmd location is-location-enabled")),
    Task("location_off", "Выключи геолокацию", "easy", ["cmd location set-location-enabled true"],
         lambda d, a: "false" in d.shell("cmd location is-location-enabled")),
    # --- настройки поглубже ---
    Task("autobright_off", "Выключи адаптивную яркость", "medium", [f"{S} system screen_brightness_mode 1"],
         setting("system", "screen_brightness_mode", lambda v: v == "0")),
    Task("autobright_on", "Включи адаптивную яркость", "medium", [f"{S} system screen_brightness_mode 0"],
         setting("system", "screen_brightness_mode", lambda v: v == "1")),
    Task("timeout_5m", "Сделай так, чтобы экран гас через 5 минут бездействия", "medium",
         [f"{S} system screen_off_timeout 60000"],
         setting("system", "screen_off_timeout", lambda v: v == "300000")),
    Task("timeout_30s", "Поставь отключение экрана через 30 секунд", "medium",
         [f"{S} system screen_off_timeout 300000"],
         setting("system", "screen_off_timeout", lambda v: v == "30000")),
    # На Android 16 у этих настроек «теневые» ключи: ползунок шрифта читает и device_font_scale, а переключатель
    # вибрации при касании — haptic_feedback_intensity. В первой версии бенчмарк менял не те ключи,
    # интерфейс показывал другое, и агент честно отвечал «уже сделано» — а проверка считала провалом
    Task("font_big", "Увеличь размер шрифта", "medium", [f"{S} system font_scale 1.0", f"{S} system device_font_scale 1.0"],
         setting("system", "font_scale", lambda v: float(v) > 1.0)),
    Task("font_default", "Верни стандартный размер шрифта", "medium",
         [f"{S} system font_scale 1.3", f"{S} system device_font_scale 1.3"],
         setting("system", "font_scale", lambda v: abs(float(v) - 1.0) < 0.01)),
    Task("haptic_off", "Отключи вибрацию при касании экрана", "medium",
         [f"{S} system haptic_feedback_intensity 2", f"{S} system haptic_feedback_enabled 1"],
         setting("system", "haptic_feedback_intensity", lambda v: v == "0")),
    # --- приложения ---
    Task("alarm_715", "Поставь будильник на 7:15", "medium", CLOCK_RESET, alarm_at("07:15")),
    Task("alarm_645", "Заведи будильник на 6:45 утра", "medium", CLOCK_RESET, alarm_at("06:45")),
    Task("calc_mul", "Посчитай на калькуляторе 1234 × 56 и скажи ответ", "medium", [],
         answer_has("69104", "69 104")),
    Task("calc_pct", "Сколько будет 15% от 2400? Посчитай на калькуляторе", "medium", [], answer_has("360")),
    Task("contact", f"Создай контакт «{CONTACT}» с номером +7 900 123-45-67", "medium",
         [delete_contact(CONTACT)], contact_exists(CONTACT)),
    Task("browser", "Открой в браузере сайт example.com", "medium", ["am force-stop org.lineageos.jelly"],
         # страница example.com сменилась в 2026: заголовка «Example Domain» больше нет — проверяем по тексту
         on_screen("Example Domain", "for use in documentation examples")),
    # --- вопросы: проверяем ответ агента ---
    Task("info_android", "Какая версия Android на этом телефоне?", "easy", [], answer_has("16")),
    Task("info_battery", "Сколько сейчас процентов заряда батареи?", "easy", [], battery_in_answer),
    Task("info_model", "Как называется модель этого телефона в настройках?", "easy", [],
         answer_has("LE2110", "OnePlus 9", "lemonade")),
    Task("info_build", "Какой номер сборки указан в настройках телефона?", "medium", [], answer_has("BP4A")),
    # --- посложнее: несколько приложений или шагов рассуждения ---
    Task("play_search", "Открой Play Маркет и найди там приложение Википедия, но ничего не устанавливай", "hard",
         ["am force-stop com.android.vending"],
         lambda d, a: "com.android.vending" in (x := d.ui_xml()) and ("Wikipedia" in x or "Википедия" in x)),
    Task("chain_contact", f"Узнай версию Android и создай контакт с именем «Android <версия>», без номера", "hard",
         [delete_contact(CHAIN_CONTACT)], contact_exists(CHAIN_CONTACT)),
    Task("calc_then_alarm", "Посчитай на калькуляторе 3 + 4 и поставь будильник на столько же часов утра, ровно",
         "hard", CLOCK_RESET, alarm_at("07:00")),
]

# всё, что после задачи стоит вернуть как было
RESTORE_KEYS = [("system", "screen_off_timeout"), ("system", "font_scale"), ("system", "device_font_scale"),
                ("system", "accelerometer_rotation"), ("system", "screen_brightness_mode"),
                ("system", "haptic_feedback_enabled"), ("system", "haptic_feedback_intensity"), ("global", "zen_mode")]
