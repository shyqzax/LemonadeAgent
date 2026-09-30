"""Восприятие: дерево UI → компактный пронумерованный список элементов; скриншот → JPEG с теми же номерами."""
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
MAX_LABEL = 80
MARK = (255, 0, 90)


@dataclass
class Element:
    id: int
    cls: str                          # короткое имя класса: Button, TextView, Switch…
    label: str                        # текст / описание / тексты вложенных элементов
    res_id: str                       # короткий resource-id (показываем, если нет подписи)
    bounds: tuple[int, int, int, int]
    flags: tuple[str, ...]            # click, edit, scroll, sel, on/off

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    def line(self) -> str:
        s = f"[{self.id}] {self.cls}"
        if self.label:
            s += f' "{self.label}"'
        elif self.res_id:
            s += f" id={self.res_id}"
        if self.flags:
            s += " {" + ",".join(self.flags) + "}"
        return s


def _clean(s: str) -> str:
    s = " ".join(s.split())
    return s if len(s) <= MAX_LABEL else s[:MAX_LABEL - 1] + "…"


def _own_label(node) -> str:
    return _clean(node.get("text", "") or node.get("content-desc", ""))


def _is_clickable(node) -> bool:
    return node.get("clickable") == "true" or node.get("long-clickable") == "true"


def _free_texts(node) -> list[str]:
    """Тексты потомков, кроме тех, что внутри вложенных кликабельных элементов: те будут в списке отдельно."""
    out = []
    for child in node.findall("node"):
        if _is_clickable(child):
            continue
        if t := _own_label(child):
            out.append(t)
        out.extend(_free_texts(child))
    return out


def parse_ui(xml: str, max_elements: int = 150) -> tuple[str, list[Element]]:
    """Вернёт (пакет текущего приложения, элементы). Оставляем только то, что можно нажать или прочитать."""
    if not xml:
        return "", []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return "", []
    first = root.find("node")
    package = first.get("package", "") if first is not None else ""
    out: list[Element] = []

    def walk(node, covered: bool):
        if len(out) >= max_elements:
            return
        a = node.attrib
        m = _BOUNDS.fullmatch(a.get("bounds", ""))
        box = tuple(map(int, m.groups())) if m else (0, 0, 0, 0)
        visible = box[2] - box[0] >= 4 and box[3] - box[1] >= 4
        cls = a.get("class", "").rsplit(".", 1)[-1]
        clickable = _is_clickable(node)
        editable = cls.endswith("EditText")
        scrollable = a.get("scrollable") == "true"
        checkable = a.get("checkable") == "true"
        label = _own_label(node)
        covers = False
        if clickable and not label:
            # кликабельная строка/карточка без подписи берёт тексты детей, а сами дети дальше не дублируются
            texts = _free_texts(node)
            if 0 < len(texts) <= 4:
                label, covers = _clean(" / ".join(texts)), True
        interactive = clickable or editable or scrollable or checkable
        if visible and (interactive or (label and not covered)):
            flags = [f for f, on in (("click", clickable), ("edit", editable), ("scroll", scrollable),
                                     ("sel", a.get("selected") == "true")) if on]
            if checkable:
                flags.append("on" if a.get("checked") == "true" else "off")
            res_id = a.get("resource-id", "").rsplit("/", 1)[-1]
            out.append(Element(len(out) + 1, cls, label, res_id, box, tuple(flags)))
        for child in node.findall("node"):
            # текст скрыт, если его забрал ближайший кликабельный предок
            walk(child, covers if clickable else covered)

    for top in root.findall("node"):
        walk(top, False)
    return package, out


def describe(package: str, elements: list[Element]) -> str:
    head = f"Приложение: {package or 'неизвестно'}"
    if not elements:
        return head + "\n(дерево UI пустое — ориентируйся по скриншоту и нажимай по координатам x,y)"
    return head + "\n" + "\n".join(e.line() for e in elements)


def png_size(png: bytes) -> tuple[int, int]:
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


def render(png: bytes, elements: list[Element] | None = None,
           max_width: int = 720) -> tuple[bytes, float, tuple[int, int]]:
    """Уменьшает скриншот (экономия токенов) и, если даны элементы, подписывает их номерами (Set-of-Mark).
    Возвращает (jpeg, масштаб картинка/экран, размер картинки)."""
    from PIL import Image, ImageDraw, ImageFont  # импорт здесь: режим «только дерево» работает и без Pillow

    img = Image.open(io.BytesIO(png)).convert("RGB")
    scale = min(1.0, max_width / img.width)
    if scale < 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    if elements:
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default(size=14)
        except TypeError:  # Pillow < 10.1
            font = ImageFont.load_default()
        for e in elements:
            x1, y1, x2, y2 = (round(v * scale) for v in e.bounds)
            draw.rectangle((x1, y1, x2, y2), outline=MARK, width=2)
            tag = str(e.id)
            draw.rectangle((x1, y1, x1 + draw.textlength(tag, font=font) + 6, y1 + 17), fill=MARK)
            draw.text((x1 + 3, y1 + 1), tag, fill="white", font=font)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=75)
    return buf.getvalue(), scale, img.size
