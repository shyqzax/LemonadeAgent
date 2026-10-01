# Работает внутри Termux: (пере)запускает бота в фоне, отвязав от adb-сессии, чтобы он жил после отключения кабеля
cd "$HOME/LemonadeAgent" || exit 1
pkill -f phone/run_bot.sh 2>/dev/null
pkill -f interfaces.telegram_bot 2>/dev/null
sleep 1
mkdir -p logs
nohup /system/bin/setsid bash phone/run_bot.sh > /dev/null 2>&1 < /dev/null &
sleep 3
pgrep -f interfaces.telegram_bot > /dev/null && echo "бот запущен" || { echo "бот не запустился:"; tail -5 logs/bot.log; }
