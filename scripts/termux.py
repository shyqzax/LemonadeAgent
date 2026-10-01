"""Выполнить команды внутри Termux на телефоне прямо с ПК — через adb и root, без набора текста на телефоне.

    python scripts/termux.py "pkg install -y python"
    python scripts/termux.py "cd ~/LemonadeAgent && python -m interfaces.cli 'включи тёмную тему'"

Команда пишется во временный скрипт, тот копируется на телефон и запускается от имени пользователя Termux
с его окружением (PREFIX, PATH, HOME…), как если бы её набрали в самом Termux.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

T = "/data/data/com.termux/files"
JOB = "/data/local/tmp/lemonade_job.sh"
WRAPPER = "/data/local/tmp/lemonade_tx.sh"
WRAPPER_SRC = f"""#!/system/bin/sh
# запускает скрипт $1 от имени пользователя Termux в окружении Termux.
# Группа 3003 (inet) даёт доступ в сеть — без неё не работает даже DNS; 9997 (everybody) есть у всех приложений
TUID=$(stat -c %u /data/data/com.termux)
exec su -g "$TUID" -G 3003 -G 9997 "$TUID" -c "env -i HOME={T}/home PREFIX={T}/usr TMPDIR={T}/usr/tmp PATH={T}/usr/bin \\
LANG=en_US.UTF-8 TERM=xterm-256color LD_PRELOAD={T}/usr/lib/libtermux-exec-ld-preload.so \\
{T}/usr/bin/bash -l $1"
"""


def adb(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["adb", *args], **kw)


def push_text(text: str, remote: str):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", suffix=".sh", delete=False) as f:
        f.write(text)
    try:
        adb("push", f.name, remote, capture_output=True, check=True)
    finally:
        Path(f.name).unlink()


def run(command: str) -> int:
    """Выполняет команду в Termux, печатает вывод по мере появления, возвращает код выхода."""
    push_text(WRAPPER_SRC, WRAPPER)
    push_text("set -e\n" + command + "\n", JOB)
    adb("shell", f"chmod 644 {JOB} {WRAPPER}", check=True)
    p = subprocess.Popen(["adb", "shell", f"su -c 'sh {WRAPPER} {JOB}'"], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    for line in p.stdout:
        sys.stdout.write(line.decode("utf-8", "replace"))
        sys.stdout.flush()
    return p.wait()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(run(sys.argv[1]))
