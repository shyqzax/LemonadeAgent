"""Проверки без телефона и без сети: python tests/test_offline.py (или pytest)."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import safety  # noqa: E402
from agent.brain import parse_action  # noqa: E402
from agent.perception import Element, parse_ui  # noqa: E402

XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation="0">
<node text="" resource-id="" class="android.widget.FrameLayout" package="com.android.settings" content-desc="" checkable="false" checked="false" clickable="false" scrollable="false" selected="false" bounds="[0,0][1080,2400]">
  <node text="" resource-id="com.android.settings:id/up" class="android.widget.ImageButton" package="com.android.settings" content-desc="Navigate up" checkable="false" checked="false" clickable="true" scrollable="false" selected="false" bounds="[0,100][140,240]" />
  <node text="Display" resource-id="android:id/title" class="android.widget.TextView" package="com.android.settings" content-desc="" checkable="false" checked="false" clickable="false" scrollable="false" selected="false" bounds="[160,120][600,220]" />
  <node text="" resource-id="com.android.settings:id/recycler_view" class="androidx.recyclerview.widget.RecyclerView" package="com.android.settings" content-desc="" checkable="false" checked="false" clickable="false" scrollable="true" selected="false" bounds="[0,260][1080,2400]">
    <node text="" resource-id="" class="android.widget.LinearLayout" package="com.android.settings" content-desc="" checkable="false" checked="false" clickable="true" scrollable="false" selected="false" bounds="[0,260][1080,460]">
      <node text="Dark theme" resource-id="android:id/title" class="android.widget.TextView" package="com.android.settings" content-desc="" checkable="false" checked="false" clickable="false" scrollable="false" selected="false" bounds="[60,290][800,360]" />
      <node text="Will never turn on automatically" resource-id="android:id/summary" class="android.widget.TextView" package="com.android.settings" content-desc="" checkable="false" checked="false" clickable="false" scrollable="false" selected="false" bounds="[60,360][800,430]" />
      <node text="" resource-id="android:id/switch_widget" class="android.widget.Switch" package="com.android.settings" content-desc="" checkable="true" checked="false" clickable="false" scrollable="false" selected="false" bounds="[900,310][1020,410]" />
    </node>
    <node text="" resource-id="" class="android.view.View" package="com.android.settings" content-desc="" checkable="false" checked="false" clickable="false" scrollable="false" selected="false" bounds="[0,460][1080,460]" />
  </node>
</node>
</hierarchy>"""


def test_parse_ui():
    package, elements = parse_ui(XML)
    assert package == "com.android.settings"
    assert [e.line() for e in elements] == [
        '[1] ImageButton "Navigate up" {click}',
        '[2] TextView "Display"',
        '[3] RecyclerView id=recycler_view {scroll}',
        '[4] LinearLayout "Dark theme / Will never turn on automatically" {click}',
        '[5] Switch id=switch_widget {off}',
    ]
    assert elements[3].center == (540, 360)


def _node(cls, bounds, text="", clickable=False, children=""):
    return (f'<node text="{text}" resource-id="" class="android.widget.{cls}" package="com.android.settings" '
            f'content-desc="" checkable="false" checked="false" clickable="{str(clickable).lower()}" '
            f'scrollable="false" selected="false" bounds="{bounds}">{children}</node>')


def test_parse_ui_nested_clickable():
    # Результат поиска в настройках OxygenOS: кликабельная строка с вложенным кликабельным заголовком.
    # Раньше строка забирала и текст заголовка, агент путался и жал в заголовок, который ничего не делает.
    header = _node("LinearLayout", "[48,385][1032,476]", clickable=True,
                   children=_node("TextView", "[96,400][900,460]", "Экран и яркость"))
    row = _node("LinearLayout", "[48,385][1032,667]", clickable=True, children=header
                + _node("TextView", "[96,490][900,560]", "Режим затемнения")
                + _node("TextView", "[96,570][900,640]", "Экран и яркость"))
    _, elements = parse_ui(f'<?xml version="1.0"?><hierarchy rotation="0">{row}</hierarchy>')
    assert [e.line() for e in elements] == [
        '[1] LinearLayout "Режим затемнения / Экран и яркость" {click}',
        '[2] LinearLayout "Экран и яркость" {click}',
    ]


def test_parse_ui_broken():
    assert parse_ui("") == ("", [])
    assert parse_ui("<not xml") == ("", [])


def test_parse_action():
    assert parse_action('```json\n{"thought": "x", "action": "tap", "id": 3}\n```') == \
        {"thought": "x", "action": "tap", "id": 3}
    assert parse_action('Sure! {"action": "home"}') == {"action": "home"}
    assert parse_action("no json here")["action"] == "invalid"
    assert parse_action('{"id": 3}')["action"] == "invalid"


def test_safety():
    el = lambda label: Element(1, "Button", label, "", (0, 0, 10, 10), ("click",))  # noqa: E731
    assert safety.needs_confirmation("tap", el("Отправить"))
    assert safety.needs_confirmation("tap", el("Pay now"))
    assert safety.needs_confirmation("tap", el("Dark theme")) is None
    assert safety.needs_confirmation("tap", el("Display")) is None
    assert safety.needs_confirmation("tap", el("Удалить запрос")) is None  # очистка поиска — не удаление данных
    assert safety.needs_confirmation("tap", el("Удалить фото"))
    # окно выдачи разрешений — всегда через человека, даже безобидное «Разрешить»
    assert safety.needs_confirmation("tap", el("Разрешить"), "com.android.permissioncontroller")
    assert safety.needs_confirmation("tap", None, "com.google.android.permissioncontroller")
    assert safety.needs_confirmation("tap", None) is None
    assert safety.is_blocked_app("ru.sberbankmobile")
    assert not safety.is_blocked_app("com.android.settings")


def test_load_env(tmp_path=None):
    import os
    import tempfile

    from agent.config import load_env

    d = Path(tmp_path or tempfile.mkdtemp())
    (d / ".env").write_text('# комментарий\nLEMON_A=1\nLEMON_B = "два слова"\n\nLEMON_C=x=y\n', encoding="utf-8")
    os.environ["LEMON_A"] = "уже задано"
    load_env(d / ".env")
    assert os.environ["LEMON_A"] == "уже задано"  # заданное окружение не перезаписываем
    assert os.environ["LEMON_B"] == "два слова" and os.environ["LEMON_C"] == "x=y"


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def call(self, method, http_timeout=30, **params):
        self.sent.append((method, params))
        return {"message_id": len(self.sent)}


def _bot():
    from interfaces.telegram_bot import Bot
    started = []
    bot = Bot(FakeTelegram(), owner=42, device=None, make_agent=None)
    bot.start_task = started.append
    return bot, started


def test_bot_listens_only_to_owner():
    bot, started = _bot()
    bot.handle({"update_id": 1, "message": {"from": {"id": 666}, "text": "удали все фото"}})
    assert started == [] and bot.tg.sent == []
    bot.handle({"update_id": 2, "message": {"from": {"id": 42}, "text": "включи тёмную тему"}})
    assert started == ["включи тёмную тему"]


def test_bot_confirm_button():
    import threading
    bot, _ = _bot()
    result = []
    t = threading.Thread(target=lambda: result.append(bot.confirm("tap «Отправить»")))
    t.start()
    while not bot.pending:
        pass
    pid = bot.pending["id"]
    # чужой не может нажать «Разрешить»
    bot.handle({"update_id": 3, "callback_query": {"id": "q0", "from": {"id": 666}, "data": f"yes:{pid}"}})
    assert bot.pending and not bot.pending["event"].is_set()
    bot.handle({"update_id": 4, "callback_query": {"id": "q1", "from": {"id": 42}, "data": f"yes:{pid}",
                                                    "message": {"message_id": 1, "text": "⚠️"}}})
    t.join(2)
    assert result == [True]


def test_memory():
    import tempfile

    from agent.memory import Memory, similarity

    assert similarity("Поставь будильник на 7:15", "Заведи будильник на 6:45 утра") > 0
    assert similarity("Включи Bluetooth", "Посчитай 2+2") == 0
    m = Memory(Path(tempfile.mkdtemp()) / "m.db")
    assert m and len(m) == 0  # пустая память — всё равно «включена» (баг первого запуска бенчмарка)
    assert m.hint("Включи тёмную тему") is None
    assert m.save("Включи тёмную тему", ["open_app com.android.settings", "tap «Экран»", "tap «Тёмная тема»"])
    assert not m.save("Включи тёмную тему", ["a", "b", "c", "d"])  # длиннее — не заменяем
    assert m.save("Включи тёмную тему", ["open_app com.android.settings", "tap «Тёмная тема»"])  # короче — заменяем
    hint = m.hint("Выключи тёмную тему")
    assert hint and "tap «Тёмная тема»" in hint and len(m) == 1
    assert m.hint("Посчитай на калькуляторе 2+2") is None
    # «грязный» путь из бенчмарка с браузером: в навык идёт только переносимое
    from agent.memory import clean
    messy = ["swipe up", "tap «Браузер»", "tap «https://www.google.com/»", "type «example.com» + Enter",
             "tap в точку на скриншоте", "type «example.com» + Enter"]
    assert clean(messy) == ["swipe up", "tap «Браузер»", "tap «https://www.google.com/»", "type «example.com» + Enter"]


class FakeDevice:
    """Телефон-заглушка: экран настроек; после нажатия переключатель тёмной темы становится «on»."""

    def __init__(self):
        import io

        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (1080, 2400), "white").save(buf, "PNG")
        self.png, self.taps = buf.getvalue(), []

    def screenshot(self): return self.png

    def ui_xml(self):
        # экран меняется после каждого нажатия: иначе агент счёл бы нажатие бесполезным и выкинул его из навыка
        xml = XML.replace('text="Display"', f'text="Display {len(self.taps)}"')
        return xml.replace('checkable="true" checked="false"', 'checkable="true" checked="true"') if self.taps else xml
    def wake(self): pass
    def key(self, code): pass
    def tap(self, x, y): self.taps.append((x, y))


class FakeBrain:
    """Мозг-заглушка: жмёт «Dark theme» ([4]) и говорит «готово»; запоминает, какую подсказку получил."""
    model = "fake"

    def __init__(self):
        self.experience = []

    def decide(self, task, history, text, image, size, experience=None):
        self.experience.append(experience)
        action = {"action": "tap", "id": 4} if not history else {"action": "done", "success": True, "summary": "ok"}
        return action, "", {"prompt_tokens": 100, "completion_tokens": 10}, ""


def test_agent_learns_skill():
    import tempfile

    from agent.loop import Agent
    from agent.memory import Memory

    tmp = Path(tempfile.mkdtemp())
    brain, memory = FakeBrain(), Memory(tmp / "m.db")
    agent = Agent(FakeDevice(), brain, memory=memory, log_root=str(tmp / "logs"), settle=0)
    r1 = agent.run("Включи тёмную тему")
    assert r1["success"] and r1["skill"] == ["tap «Dark theme / Will never turn on automatically»"]
    assert r1["learned"] and len(memory) == 1 and brain.experience[0] is None
    r2 = agent.run("Выключи тёмную тему")
    assert r2["memory_hint"] and "Dark theme" in brain.experience[-1]
    assert r1["cost_usd"] > 0


class TwoStepBrain(FakeBrain):
    """«Назад» ([1]), потом «Dark theme» ([4]), потом «готово» — по числу шагов в истории."""

    def decide(self, task, history, text, image, size, experience=None):
        self.experience.append(experience)
        action = [{"action": "tap", "id": 1}, {"action": "tap", "id": 4}][len(history)] if len(history) < 2 \
            else {"action": "done", "success": True, "summary": "ok"}
        return action, "", {"prompt_tokens": 100, "completion_tokens": 10}, ""


def test_agent_replays_known_skill():
    import tempfile

    from agent.loop import Agent
    from agent.memory import Memory

    tmp = Path(tempfile.mkdtemp())
    brain, memory = TwoStepBrain(), Memory(tmp / "m.db")
    agent = Agent(FakeDevice(), brain, memory=memory, log_root=str(tmp / "logs"), settle=0)
    r1 = agent.run("Включи тёмную тему")
    assert r1["llm_calls"] == 3 and r1["replayed"] == 0 and len(r1["skill"]) == 2
    # та же задача ещё раз: первый шаг навыка повторяется без модели, решающий последний — за моделью
    r2 = agent.run("Включи тёмную тему")
    assert r2["success"] and r2["replayed"] == 1 and r2["llm_calls"] == 2 and r2["cost_usd"] < r1["cost_usd"]


def test_cost():
    from datetime import datetime, timezone

    from agent.cost import cost_usd, is_peak

    usage = {"prompt_cache_hit_tokens": 1_000_000, "prompt_cache_miss_tokens": 1_000_000, "completion_tokens": 1_000_000}
    night = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)   # среда, 12:00 UTC — не пик
    peak = datetime(2026, 10, 1, 7, 0, tzinfo=timezone.utc)     # среда, 07:00 UTC — пик
    assert not is_peak(night) and is_peak(peak) and not is_peak(datetime(2026, 10, 3, 7, tzinfo=timezone.utc))
    assert abs(cost_usd(usage, night) - (0.003 + 0.15 + 0.6)) < 1e-9
    assert abs(cost_usd(usage, peak) - (0.006 + 0.30 + 1.2)) < 1e-9


def test_bench_tasks():
    from bench.tasks import TASKS

    ids = [t.id for t in TASKS]
    assert len(ids) == len(set(ids)) and len(TASKS) >= 25
    banned = re.compile(r"wi-?fi|режим полёта|airplane|vpn", re.I)  # задачи, рвущие связь, не берём
    assert not [t.id for t in TASKS if banned.search(t.text)]


def test_render():
    try:
        from PIL import Image
    except ImportError:
        print("  (Pillow не установлен — пропускаю render)")
        return
    import io

    from agent.perception import png_size, render

    buf = io.BytesIO()
    Image.new("RGB", (1080, 2400), "white").save(buf, "PNG")
    png = buf.getvalue()
    assert png_size(png) == (1080, 2400)
    _, elements = parse_ui(XML)
    jpeg, scale, size = render(png, elements)
    assert jpeg[:2] == b"\xff\xd8" and size == (720, 1600) and abs(scale - 720 / 1080) < 1e-9


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
