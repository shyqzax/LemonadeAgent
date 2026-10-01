"""Главный цикл: смотрим на экран → мозг выбирает действие → проверка безопасности → действие → лог.

Каждый запуск пишется в logs/<время>_<задача>/: скриншоты, что видел мозг, его ответы и итог.
Это и материал для видео, и датасет «экран → действие» для дообучения локальной модели.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import safety
from .cost import cost_usd
from .device import KEY_BACK, KEY_ENTER, KEY_HOME, DeviceError
from .perception import Element, describe, parse_ui, png_size, render

MODES = ("both", "tree", "screen")  # что видит мозг: дерево + скриншот / только дерево / только скриншот
PASSIVE = ("wait", "ask_user", "done", "invalid")  # после этих действий экран и не должен меняться


@dataclass
class Observation:
    package: str
    elements: list[Element]
    xml: str
    png: bytes
    screen: tuple[int, int]               # размер экрана в пикселях
    text: str | None                      # что уходит в мозг текстом
    image: bytes | None                   # что уходит в мозг картинкой (JPEG)
    image_size: tuple[int, int] | None
    scale: float                          # пиксели картинки / пиксели экрана


class Agent:
    def __init__(self, device, brain, mode: str = "both", max_steps: int = 25, confirm=None, ask=None,
                 on_step=None, should_stop=None, log_root: str = "logs", settle: float = 1.0,
                 memory=None, autosave: bool = True, replay: bool = True):
        assert mode in MODES, mode
        self.device, self.brain, self.mode, self.max_steps = device, brain, mode, max_steps
        # память-навыки; autosave — запоминать путь, когда агент сам сказал «готово».
        # Бенчмарк выключает autosave и сохраняет только проверенные успехи.
        # replay — если ровно эта задача уже решалась, пройти знакомый путь без модели (кроме последнего шага)
        self.memory, self.autosave, self.replay = memory, autosave, replay
        self.confirm = confirm or (lambda reason: False)  # без человека опасное запрещено
        self.ask = ask or (lambda question: "пользователь недоступен")
        self.on_step = on_step or (lambda record: None)
        self.should_stop = should_stop or (lambda: False)  # аварийная остановка (/stop в Telegram)
        self.log_root, self.settle = Path(log_root), settle

    def observe(self) -> Observation:
        # скриншот и дерево UI снимаются по ~2 с каждый, поэтому параллельно
        with ThreadPoolExecutor(2) as pool:
            png_job, xml_job = pool.submit(self.device.screenshot), pool.submit(self.device.ui_xml)
            png, xml = png_job.result(), xml_job.result()
        package, elements = parse_ui(xml)
        text = image = size = None
        scale = 1.0
        if self.mode in ("both", "tree"):
            text = describe(package, elements)
        if self.mode != "tree" or not elements:  # в режиме «только дерево» скриншот — запасной вариант
            image, scale, size = render(png, elements if self.mode == "both" else None)
        return Observation(package, elements, xml, png, png_size(png), text, image, size, scale)

    def run(self, task: str) -> dict:
        run_dir = self.log_root / f"{datetime.now():%Y%m%d-%H%M%S}_{_slug(task)}"
        run_dir.mkdir(parents=True, exist_ok=True)
        history: list[str] = []
        skill: list[str] = []  # удачный путь — пойдёт в память, если задача решена
        prev_screen, prev_action, skill_added_at = None, None, None
        experience = self.memory.hint(task) if self.memory is not None else None
        known = self.memory.exact(task) if self.memory is not None and self.replay else None
        result = {"task": task, "mode": self.mode, "model": self.brain.model, "success": False,
                  "summary": "прервано", "steps": 0, "prompt_tokens": 0, "completion_tokens": 0,
                  "cost_usd": 0.0, "memory_hint": experience is not None, "replayed": 0, "llm_calls": 0}
        t0 = time.time()
        try:
            self.device.wake()
            with open(run_dir / "steps.jsonl", "w", encoding="utf-8") as log:
                first = 1
                if known and len(known) > 1:
                    # навигацию повторяем сами, решающий последний шаг — за моделью: состояние могло быть другим
                    history, done = self._replay(known[:-1], log, result)
                    skill += done
                    first = len(history) + 1
                    result["steps"] = len(history)
                for step in range(first, self.max_steps + 1):
                    if self.should_stop():
                        result["summary"] = "остановлено человеком"
                        break
                    ts = time.time()
                    result["steps"] = step
                    obs = self.observe()
                    (run_dir / f"{step:02d}.png").write_bytes(obs.png)
                    (run_dir / f"{step:02d}.xml").write_text(obs.xml, encoding="utf-8")
                    if obs.image:
                        (run_dir / f"{step:02d}_seen.jpg").write_bytes(obs.image)
                    screen = [e.line() for e in obs.elements]
                    if screen and screen == prev_screen and prev_action not in PASSIVE:
                        history[-1] += " — экран НЕ изменился"
                        if skill_added_at == step - 1:
                            skill.pop()  # бесполезный шаг в навык не берём
                    prev_screen = screen
                    if safety.is_blocked_app(obs.package):
                        self.device.key(KEY_HOME)
                        history.append(f"{step}. оказался в запрещённом приложении {obs.package} — вернулся домой")
                        continue

                    action, raw, usage, reasoning = self.brain.decide(task, history, obs.text, obs.image,
                                                                       obs.image_size, experience)
                    result["llm_calls"] += 1
                    outcome = self.act(action, obs)
                    prev_action = action.get("action")
                    if prev_action not in PASSIVE and not outcome.startswith(("ошибка", "человек запретил", "запрещено")):
                        skill.append(_skill_step(action, _find(obs.elements, action.get("id")), outcome))
                        skill_added_at = step

                    for k in ("prompt_tokens", "completion_tokens"):
                        result[k] += usage.get(k) or 0
                    step_cost = cost_usd(usage)
                    result["cost_usd"] += step_cost
                    thought = str(action.get("thought", ""))[:200]
                    short = {k: v for k, v in action.items() if k != "thought"}
                    history.append(f"{step}. {thought} → {json.dumps(short, ensure_ascii=False)} → {outcome}")
                    record = {"step": step, "package": obs.package,
                              "elements": [[e.line(), e.bounds] for e in obs.elements],
                              "reasoning": reasoning, "raw": raw, "action": action, "outcome": outcome, "usage": usage,
                              "cost_usd": step_cost, "seconds": round(time.time() - ts, 2)}
                    log.write(json.dumps(record, ensure_ascii=False) + "\n")
                    log.flush()
                    self.on_step(record)

                    if action.get("action") == "done":
                        result["success"] = bool(action.get("success", True))
                        result["summary"] = str(action.get("summary", ""))
                        break
                    time.sleep(self.settle)
                else:
                    result["summary"] = "лимит шагов исчерпан"
            result["skill"] = skill
            if self.memory is not None and self.autosave and result["success"]:
                result["learned"] = self.memory.save(task, skill)
        finally:
            result["seconds"] = round(time.time() - t0, 1)
            result["cost_usd"] = round(result["cost_usd"], 6)
            result["log_dir"] = str(run_dir)
            (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def _replay(self, steps: list[str], log, result: dict) -> tuple[list[str], list[str]]:
        """Повторяет шаги навыка без модели, находя элементы по подписи. Не нашёл элемент или действие
        запрещено — останавливается, и дальше думает модель (повторённое видно ей в истории)."""
        history, done = [], []
        for i, s in enumerate(steps, 1):
            if self.should_stop():
                break
            ts = time.time()
            obs = self.observe()
            outcome = self._replay_step(s, obs)
            history.append(f"{i}. [повтор навыка] {s} → {outcome}")
            record = {"step": i, "package": obs.package, "action": {"action": "replay", "thought": f"повторяю: {s}"},
                      "replay": s, "outcome": outcome, "cost_usd": 0.0, "seconds": round(time.time() - ts, 2)}
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            log.flush()
            self.on_step(record)
            if outcome.startswith(("не нашёл", "ошибка", "человек запретил", "запрещено")):
                history[-1] += " — повтор прерван, дальше решаю сам"
                break
            done.append(s)
            time.sleep(self.settle)
        result["replayed"] = len(done)
        return history, done

    def _replay_step(self, s: str, obs: Observation) -> str:
        if m := re.match(r"^(tap|long_press) «(.*)»$", s):
            el = _match_label(obs.elements, m.group(2))
            return self.act({"action": m.group(1), "id": el.id}, obs) if el else f"не нашёл «{m.group(2)}» на экране"
        if m := re.match(r"^type «(.*)»( \+ Enter)?$", s):
            return self.act({"action": "type", "text": m.group(1), "enter": bool(m.group(2))}, obs)
        if s.startswith("open_app "):
            return self.act({"action": "open_app", "app": s.split(" ", 1)[1]}, obs)
        if s.startswith("swipe "):
            return self.act({"action": "swipe", "direction": s.split(" ", 1)[1]}, obs)
        if s in ("back", "home", "enter"):
            return self.act({"action": s}, obs)
        return f"ошибка: не умею повторять «{s}»"

    def act(self, a: dict, obs: Observation) -> str:
        """Выполняет действие и возвращает короткий итог — он попадёт в историю для мозга."""
        name = a.get("action")
        el = _find(obs.elements, a.get("id"))
        try:
            if name in ("tap", "long_press"):
                xy = el.center if el else _xy(a, obs)
                if xy is None:
                    return f"ошибка: нет элемента с id={a.get('id')} и не заданы x,y"
                reason = safety.needs_confirmation(name, el, obs.package)
                if reason and not self.confirm(reason):
                    return f"человек запретил: {reason}"
                (self.device.tap if name == "tap" else self.device.long_press)(*xy)
                return f"нажал [{el.id}] «{el.label}»" if el else f"нажал точку {xy}"
            if name == "type":
                if el:
                    self.device.tap(*el.center)
                    time.sleep(0.5)
                # по умолчанию текст заменяет содержимое поля; дописать — "append": true
                self.device.type_text(str(a.get("text", "")), enter=bool(a.get("enter")), clear=not a.get("append"))
                return ("дописал" if a.get("append") else "ввёл") + " текст" + (" и нажал Enter" if a.get("enter") else "")
            if name == "swipe":
                d = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}.get(a.get("direction"))
                if not d:
                    return "ошибка: direction должен быть up/down/left/right"
                w, h = obs.screen
                dx, dy = int(d[0] * w * 0.3), int(d[1] * h * 0.25)
                self.device.swipe(w // 2 - dx, h // 2 - dy, w // 2 + dx, h // 2 + dy)
                return f"свайп {a['direction']}"
            if name == "open_app":
                app = str(a.get("app", ""))
                if safety.is_blocked_app(app):
                    return f"запрещено: «{app}» в чёрном списке"
                return f"открыл {self.device.open_app(app)}"
            if name in ("back", "home", "enter"):
                self.device.key({"back": KEY_BACK, "home": KEY_HOME, "enter": KEY_ENTER}[name])
                return f"нажал {name}"
            if name == "wait":
                time.sleep(min(float(a.get("seconds", 2)), 10))
                return "подождал"
            if name == "ask_user":
                return "пользователь ответил: " + self.ask(str(a.get("question", "")))
            if name == "done":
                return "задача завершена"
            if name == "invalid":
                return "ошибка: ответ не разобран — ответь строго одним JSON-объектом"
            return f"ошибка: неизвестное действие {name!r}"
        except DeviceError as e:
            return f"ошибка устройства: {e}"
        except (TypeError, ValueError) as e:
            return f"ошибка в параметрах действия: {e}"


def _skill_step(a: dict, el: Element | None, outcome: str) -> str:
    """Шаг навыка в человекочитаемом виде — без номеров элементов, они в следующий раз будут другими."""
    name = a.get("action")
    if name in ("tap", "long_press"):
        return f"{name} «{el.label or el.res_id or el.cls}»" if el else f"{name} в точку на скриншоте"
    if name == "type":
        return f"type «{a.get('text', '')}»" + (" + Enter" if a.get("enter") else "")
    if name == "swipe":
        return f"swipe {a.get('direction')}"
    if name == "open_app":
        return "open_app " + (outcome.split()[1] if outcome.startswith("открыл ") else str(a.get("app")))
    return str(name)


def _match_label(elements: list[Element], label: str) -> Element | None:
    """Элемент с той же подписью; если такой нет — с тем же началом подписи (до « / »: хвост бывает живым,
    например «Bluetooth, подключено»). Из подходящих предпочитаем кликабельные."""
    head = label.split(" / ")[0]
    for pick in (lambda e: e.label == label, lambda e: e.label.split(" / ")[0] == head):
        found = [e for e in elements if e.label and pick(e)]
        if found:
            return next((e for e in found if "click" in e.flags), found[0])
    return None


def _find(elements: list[Element], id_) -> Element | None:
    try:
        i = int(id_)
    except (TypeError, ValueError):
        return None
    return elements[i - 1] if 1 <= i <= len(elements) else None


def _xy(a: dict, obs: Observation) -> tuple[int, int] | None:
    """Координаты из пикселей скриншота (который видел мозг) переводим в пиксели экрана."""
    try:
        x, y = float(a["x"]) / obs.scale, float(a["y"]) / obs.scale
    except (KeyError, TypeError, ValueError):
        return None
    w, h = obs.screen
    return min(max(int(x), 0), w - 1), min(max(int(y), 0), h - 1)


def _slug(task: str) -> str:
    return re.sub(r"\W+", "-", task.lower()).strip("-")[:40] or "task"
