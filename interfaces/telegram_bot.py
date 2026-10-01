"""Telegram-бот: пишешь задачу в чат — телефон выполняет её сам.

    python -m interfaces.telegram_bot          # на телефоне (Termux + root)
    python -m interfaces.telegram_bot --adb    # с ПК по USB — удобно для отладки

Слушается только TELEGRAM_ALLOWED_USER_ID. Опасные нажатия агент подтверждает кнопками в чате.
Bot API — на стандартной библиотеке (long polling), чтобы в Termux не ставить лишних пакетов.
"""
import argparse
import json
import os
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import datetime

from agent.brain import Brain
from agent.config import ROOT, load_env
from agent.device import AdbDevice, RootDevice
from agent.loop import MODES, Agent
from agent.perception import render

CONFIRM_TIMEOUT = 120  # с: не ответил на «Разрешить?» — значит нельзя
ASK_TIMEOUT = 300
PROGRESS_LINES = 20    # сколько последних шагов держать в сообщении с прогрессом

HELP = """🍋 Lemonade Agent — ИИ, который сам управляет этим телефоном.

Напиши задачу обычным текстом, например «включи тёмную тему» или «поставь будильник на 7:00».

/stop — остановить агента
/shot — прислать скриншот экрана
/status — что сейчас происходит"""

COMMANDS = [{"command": "stop", "description": "остановить агента"},
            {"command": "shot", "description": "скриншот экрана"},
            {"command": "status", "description": "что сейчас происходит"},
            {"command": "help", "description": "как пользоваться"}]


def log(text: str):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}", flush=True)


class TelegramError(RuntimeError):
    pass


class Telegram:
    """Минимальный клиент Bot API. URL с токеном никогда не попадает в сообщения об ошибках."""

    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}/"

    def _post(self, method: str, body: bytes, content_type: str, http_timeout: float):
        req = urllib.request.Request(self.base + method, body, {"Content-Type": content_type})
        try:
            with urllib.request.urlopen(req, timeout=http_timeout) as r:
                return json.load(r)["result"]
        except urllib.error.HTTPError as e:
            try:
                desc = json.loads(e.read()).get("description", "")
            except ValueError:
                desc = ""
            raise TelegramError(f"{method}: {e.code} {desc}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise TelegramError(f"{method}: нет связи ({e})") from None

    def call(self, method: str, http_timeout: float = 30, **params):
        return self._post(method, json.dumps(params).encode("utf-8"), "application/json", http_timeout)

    def send_photo(self, chat_id: int, jpeg: bytes, caption: str = ""):
        b = uuid.uuid4().hex
        body = b"".join([
            f'--{b}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode(),
            f'--{b}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1000]}\r\n'.encode(),
            f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="screen.jpg"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n".encode() + jpeg + b"\r\n",
            f"--{b}--\r\n".encode(),
        ])
        return self._post("sendPhoto", body, f"multipart/form-data; boundary={b}", 60)


class Bot:
    def __init__(self, tg: Telegram, owner: int, device, make_agent):
        self.tg, self.owner, self.device, self.make_agent = tg, owner, device, make_agent
        self.offset = 0
        self.stop_flag = threading.Event()
        self.task_thread: threading.Thread | None = None
        self.pending: dict | None = None  # ждём от человека: {"kind": "confirm"|"ask", "id", "event", "answer"}
        self.status = "жду задачу"
        self.progress_id: int | None = None
        self.progress: list[str] = []

    # --- отправка ---
    def say(self, text: str, **extra) -> dict | None:
        try:
            return self.tg.call("sendMessage", chat_id=self.owner, text=text[:4000], **extra)
        except TelegramError as e:
            log(f"не отправил сообщение: {e}")

    def send_screen(self, caption: str = ""):
        try:
            jpeg, _, _ = render(self.device.screenshot(), None, max_width=720)
            self.tg.send_photo(self.owner, jpeg, caption)
        except Exception as e:  # скриншот — не повод ронять бота
            log(f"не отправил скриншот: {e}")
            if caption:
                self.say(caption)

    def _update_progress(self):
        if not self.progress_id:
            return
        text = "\n".join(self.progress[:1] + self.progress[1:][-PROGRESS_LINES:])
        try:
            self.tg.call("editMessageText", chat_id=self.owner, message_id=self.progress_id, text=text[:4000])
        except TelegramError as e:
            if "not modified" not in str(e):
                log(f"не обновил прогресс: {e}")

    # --- что агент спрашивает у человека (вызывается из потока агента) ---
    def _wait_human(self, kind: str, text: str, timeout: float, **extra):
        pid = uuid.uuid4().hex[:8]
        event = threading.Event()
        self.pending = {"kind": kind, "id": pid, "event": event, "answer": None}
        self.say(text, **{k: (v(pid) if callable(v) else v) for k, v in extra.items()})
        answered = event.wait(timeout)
        answer = self.pending["answer"] if answered else None
        self.pending = None
        return answered, answer

    def confirm(self, reason: str) -> bool:
        if self.stop_flag.is_set():
            return False
        keyboard = lambda pid: {"inline_keyboard": [[  # noqa: E731
            {"text": "✅ Разрешить", "callback_data": f"yes:{pid}"},
            {"text": "❌ Запретить", "callback_data": f"no:{pid}"}]]}
        answered, answer = self._wait_human("confirm", f"⚠️ Агент хочет: {reason}\nРазрешить?", CONFIRM_TIMEOUT,
                                            reply_markup=keyboard)
        if not answered:
            self.say("⌛ Ответа нет — запретил.")
        return bool(answer)

    def ask(self, question: str) -> str:
        answered, answer = self._wait_human("ask", f"❓ {question}", ASK_TIMEOUT)
        return answer if answered and answer else "пользователь не ответил"

    def on_step(self, r: dict):
        a = r["action"]
        thought = str(a.get("thought", "")).strip()
        self.status = f"шаг {r['step']}: {thought[:200]}"
        self.progress.append(f"{r['step']}. {thought[:90]} → {r['outcome'][:70]}")
        self._update_progress()

    # --- задачи ---
    def busy(self) -> bool:
        return self.task_thread is not None and self.task_thread.is_alive()

    def start_task(self, task: str):
        self.stop_flag.clear()
        self.task_thread = threading.Thread(target=self.run_task, args=(task,), daemon=True)
        self.task_thread.start()

    def run_task(self, task: str):
        log(f"задача: {task}")
        self.status = f"начинаю: {task}"
        self.progress = [f"🍋 {task}"]
        msg = self.say(self.progress[0] + "\n…")
        self.progress_id = msg["message_id"] if msg else None
        agent = self.make_agent(confirm=self.confirm, ask=self.ask, on_step=self.on_step,
                                should_stop=self.stop_flag.is_set)
        try:
            r = agent.run(task)
        except Exception as e:
            log(traceback.format_exc())
            self.say(f"💥 Ошибка: {e}")
            return
        finally:
            self.status = "жду задачу"
        log(f"итог: {r['success']} {r['summary']} ({r['steps']} шагов, {r['seconds']} с)")
        icon = "✅" if r["success"] else ("⏹" if r["summary"] == "остановлено человеком" else "❌")
        self.send_screen(f"{icon} {r['summary']}\nшагов {r['steps']}, {r['seconds']} с")

    # --- входящие ---
    def resolve(self, kind: str, pid: str | None, answer):
        p = self.pending
        if p and p["kind"] == kind and (pid is None or p["id"] == pid):
            p["answer"] = answer
            p["event"].set()
            return True
        return False

    def handle(self, u: dict):
        if q := u.get("callback_query"):
            if q["from"]["id"] != self.owner:
                return
            verdict, _, pid = q.get("data", "").partition(":")
            ok = self.resolve("confirm", pid, verdict == "yes")
            self.tg.call("answerCallbackQuery", callback_query_id=q["id"],
                         text=("Разрешено" if verdict == "yes" else "Запрещено") if ok else "Уже неактуально")
            if ok and (m := q.get("message")):
                mark = "✅ разрешено" if verdict == "yes" else "❌ запрещено"
                try:
                    self.tg.call("editMessageText", chat_id=self.owner, message_id=m["message_id"],
                                 text=f"{m.get('text', '')}\n→ {mark}")
                except TelegramError:
                    pass
            return
        msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        if not text:
            return
        if msg.get("from", {}).get("id") != self.owner:
            log(f"сообщение от чужого пользователя {msg.get('from', {}).get('id')} — игнорирую")
            return
        cmd = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
        if cmd in ("/start", "/help"):
            self.say(HELP)
        elif cmd == "/stop":
            if self.busy():
                self.stop_flag.set()
                self.resolve("confirm", None, False) or self.resolve("ask", None, "остановлено")
                self.say("⏹ Останавливаю после текущего шага.")
            else:
                self.say("Агент и так ничего не делает.")
        elif cmd == "/status":
            self.say(f"Сейчас: {self.status}")
        elif cmd == "/shot":
            threading.Thread(target=self.send_screen, daemon=True).start()
        elif cmd:
            self.say("Не знаю такой команды. /help")
        elif self.resolve("ask", None, text):
            pass  # это был ответ на вопрос агента
        elif self.busy():
            self.say("Я ещё выполняю прошлую задачу. /stop — чтобы прервать её.")
        else:
            self.start_task(text)

    def run_forever(self):
        me = self.tg.call("getMe")
        log(f"бот @{me['username']} запущен, слушаюсь только пользователя {self.owner}")
        try:
            self.tg.call("setMyCommands", commands=COMMANDS)
        except TelegramError as e:
            log(f"не задал меню команд: {e}")
        self.say("🍋 Lemonade Agent на связи. Напиши задачу — /help подскажет, как.")
        while True:
            try:
                updates = self.tg.call("getUpdates", http_timeout=70, offset=self.offset, timeout=50,
                                       allowed_updates=["message", "callback_query"])
            except TelegramError as e:
                log(f"getUpdates: {e}")
                time.sleep(5)
                continue
            for u in updates:
                self.offset = u["update_id"] + 1
                try:
                    self.handle(u)
                except Exception:
                    log(traceback.format_exc())


def main():
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    load_env()
    p = argparse.ArgumentParser(description="Lemonade Agent: Telegram-бот")
    p.add_argument("--adb", action="store_true", help="управлять телефоном с ПК по USB (по умолчанию — изнутри, через su)")
    p.add_argument("--serial", help="серийный номер для --adb")
    p.add_argument("--mode", choices=MODES, default="both")
    p.add_argument("--max-steps", type=int, default=25)
    args = p.parse_args()

    token, owner = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_ALLOWED_USER_ID", "")
    if not token or not owner.isdigit():
        sys.exit("заполни TELEGRAM_BOT_TOKEN и TELEGRAM_ALLOWED_USER_ID в .env")
    device = AdbDevice(args.serial) if args.adb else RootDevice()
    brain = Brain()

    def make_agent(**callbacks):
        return Agent(device, brain, mode=args.mode, max_steps=args.max_steps, log_root=str(ROOT / "logs"), **callbacks)

    Bot(Telegram(token), int(owner), device, make_agent).run_forever()


if __name__ == "__main__":
    main()
