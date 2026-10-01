"""Слой устройства: один интерфейс для управления с ПК (AdbDevice) и прямо на телефоне (RootDevice).

Наследник задаёт только _argv(): как выполнить команду в оболочке Android. Всё остальное общее,
поэтому код агента не знает, где он запущен.
"""
import base64
import os
import re
import shlex
import shutil
import subprocess
import time

KEY_HOME, KEY_BACK, KEY_ENTER = 3, 4, 66
UI_DUMP = "/data/local/tmp/lemonade_ui.xml"
ADB_IME = "com.android.adbkeyboard/.AdbIME"  # github.com/senzhk/ADBKeyBoard — ввод Unicode через broadcast


class DeviceError(RuntimeError):
    pass


class Device:
    def _argv(self, cmd: str) -> list[str]:
        raise NotImplementedError

    def _env(self) -> dict | None:
        return None  # по умолчанию — окружение текущего процесса

    def _run(self, cmd: str, timeout: float = 30) -> bytes:
        try:
            r = subprocess.run(self._argv(cmd), capture_output=True, timeout=timeout, env=self._env())
        except subprocess.TimeoutExpired:
            raise DeviceError(f"команда не уложилась в {timeout} с: {cmd}") from None
        if r.returncode != 0 and not r.stdout:
            raise DeviceError(r.stderr.decode("utf-8", "replace").strip() or f"код выхода {r.returncode}: {cmd}")
        return r.stdout

    def shell(self, cmd: str, timeout: float = 30) -> str:
        return self._run(cmd, timeout).decode("utf-8", "replace")

    # --- восприятие ---
    def screenshot(self) -> bytes:
        png = self._run("screencap -p", timeout=15)
        if not png.startswith(b"\x89PNG"):
            raise DeviceError("screencap вернул не PNG")
        return png

    def ui_xml(self) -> str:
        """Дерево UI текущего экрана. Пустая строка, если uiautomator его не снял (анимация, видео, игра)."""
        # «; true» — пустой ответ вместо ошибки, если экран не успокоился («could not get idle state»)
        out = self.shell(f"rm -f {UI_DUMP}; uiautomator dump {UI_DUMP} >/dev/null 2>&1; cat {UI_DUMP} 2>/dev/null; true",
                         timeout=20)
        start = out.find("<?xml")
        return out[start:] if start >= 0 else ""

    def wake(self):
        """Включает экран и убирает экран блокировки (без пароля) — команда может прийти, когда телефон спит."""
        self.shell("input keyevent 224; wm dismiss-keyguard")
        time.sleep(0.8)

    # --- действия ---
    def tap(self, x: int, y: int):
        self.shell(f"input tap {x} {y}")

    def long_press(self, x: int, y: int, ms: int = 800):
        self.shell(f"input swipe {x} {y} {x} {y} {ms}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 350):
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {ms}")

    def key(self, code: int):
        self.shell(f"input keyevent {code}")

    def current_ime(self) -> str:
        return self.shell("settings get secure default_input_method").strip()

    def type_text(self, text: str, enter: bool = False):
        if text.isascii():
            # у `input text` пробел кодируется как %s
            self.shell("input text " + shlex.quote(text.replace(" ", "%s")))
            if enter:
                self.key(KEY_ENTER)
            return
        # Кириллицу `input text` не умеет. Печатаем через ADBKeyBoard, включая её только на время ввода,
        # чтобы у человека оставалась обычная клавиатура
        prev = self.current_ime()
        self.shell(f"ime enable {ADB_IME} >/dev/null 2>&1; ime set {ADB_IME} >/dev/null 2>&1")
        try:
            if "adbkeyboard" not in self.current_ime():
                raise DeviceError("не удалось включить ADBKeyBoard (не установлена?) — пиши латиницей")
            time.sleep(0.7)  # клавиатуре нужно подключиться к полю ввода
            b64 = base64.b64encode(text.encode("utf-8")).decode()
            self.shell(f"am broadcast -a ADB_INPUT_B64 --es msg {b64}")
            if enter:
                # Enter жмём, пока активна невидимая ADBKeyBoard: если вернуть Gboard раньше,
                # она всплывёт над полем и закроет результаты (так было в задаче про погоду)
                self.key(KEY_ENTER)
                time.sleep(1.0)
        finally:
            if prev and "adbkeyboard" not in prev:
                self.shell(f"ime set {shlex.quote(prev)} >/dev/null 2>&1")

    def open_app(self, app: str) -> str:
        """Открыть приложение по пакету ('com.android.settings') или части имени ('settings', 'clock')."""
        out = self.shell("pm list packages")
        pkgs = [line[8:].strip() for line in out.splitlines() if line.startswith("package:")]
        q = app.strip().lower().replace(" ", "")
        candidates = [q] if q in pkgs else sorted((p for p in pkgs if q and q in p.lower()), key=len)
        for pkg in candidates[:5]:
            if "Events injected" in self.shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1 2>&1"):
                return pkg
        hint = f"; похожие пакеты без иконки: {', '.join(candidates[:5])}" if candidates else ""
        raise DeviceError(f"не нашёл приложение '{app}'{hint}")


class AdbDevice(Device):
    """Телефон подключён к ПК по USB, команды идут через adb."""

    def __init__(self, serial: str | None = None, adb: str = "adb"):
        self.prefix = [adb] + (["-s", serial] if serial else []) + ["exec-out"]

    def _argv(self, cmd):
        return self.prefix + [cmd]


class RootDevice(Device):
    """Агент живёт прямо на телефоне (Termux + root): команды идут через su.

    В PATH Termux нет системного su, поэтому ищем его сами. При первом вызове Magisk спросит на экране,
    дать ли Termux права суперпользователя.

    В окружении Termux нет системных переменных Android (BOOTCLASSPATH, ANDROID_ROOT…), а без них Java-утилиты
    вроде uiautomator молча падают. Берём их у zygote — родителя всех приложений — и передаём в каждую команду."""

    ANDROID_ENV = re.compile(r"^(ANDROID_(?!SOCKET)\w+|\w*CLASSPATH|STANDALONE_SYSTEMSERVER_JARS|EXTERNAL_STORAGE)$")

    def __init__(self):
        self.su = shutil.which("su") or next((p for p in ("/system/bin/su", "/debug_ramdisk/su", "/sbin/su")
                                              if os.path.exists(p)), "su")
        self.env = None

    def _env(self):
        if self.env is None:
            self.env = dict(os.environ)
            if "BOOTCLASSPATH" not in self.env:
                raw = subprocess.run([self.su, "-c", "cat /proc/$(pidof zygote64 || pidof zygote)/environ"],
                                     capture_output=True, timeout=15).stdout
                for kv in raw.decode("utf-8", "replace").split("\0"):
                    key, _, value = kv.partition("=")
                    if self.ANDROID_ENV.match(key):
                        self.env[key] = value
        return self.env

    def _argv(self, cmd):
        return [self.su, "-c", cmd]
