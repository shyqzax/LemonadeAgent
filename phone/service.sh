#!/system/bin/sh
# Lemonade Agent: автозапуск Telegram-бота при включении телефона.
# Ставится в /data/adb/service.d/lemonade.sh — Magisk запускает такие скрипты от root после загрузки.
T=/data/data/com.termux/files

until [ "$(getprop sys.boot_completed)" = "1" ]; do sleep 5; done
sleep 20  # даём подняться сети

# процессор не засыпает — иначе с погасшим экраном бот не услышит Telegram; Termux не душит экономия батареи
echo lemonade > /sys/power/wake_lock
dumpsys deviceidle whitelist +com.termux > /dev/null 2>&1

# бот работает от имени пользователя Termux; группа 3003 (inet) нужна для доступа в сеть
TUID=$(stat -c %u /data/data/com.termux)
su -g "$TUID" -G 3003 -G 9997 "$TUID" -c "env -i HOME=$T/home PREFIX=$T/usr TMPDIR=$T/usr/tmp PATH=$T/usr/bin \
LANG=en_US.UTF-8 LD_PRELOAD=$T/usr/lib/libtermux-exec-ld-preload.so $T/usr/bin/bash -l $T/home/LemonadeAgent/phone/start_bot.sh"
