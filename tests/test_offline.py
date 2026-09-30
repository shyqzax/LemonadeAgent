"""Проверки без телефона и без сети: python tests/test_offline.py (или pytest)."""
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
    assert safety.needs_confirmation("tap", None) is None
    assert safety.is_blocked_app("ru.sberbankmobile")
    assert not safety.is_blocked_app("com.android.settings")


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
