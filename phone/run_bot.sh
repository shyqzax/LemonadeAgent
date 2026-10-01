# Работает внутри Termux: держит Telegram-бота запущенным и перезапускает, если тот упал. Лог — logs/bot.log
cd "$HOME/LemonadeAgent" || exit 1
mkdir -p logs
while true; do
  python -m interfaces.telegram_bot >> logs/bot.log 2>&1
  echo "$(date '+%F %T') бот завершился с кодом $?, перезапуск через 10 с" >> logs/bot.log
  sleep 10
done
