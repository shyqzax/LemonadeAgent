# Работает внутри Termux: прогоняет бенчмарк в фоне, отвязав от adb — можно отключить кабель.
# Аргументы передаются в bench.run_bench, вывод — в logs/bench/<имя>.out
#   bash phone/bench.sh --name memory --rounds 3 --memory
cd "$HOME/LemonadeAgent" || exit 1
name=$(echo "$@" | grep -oE -- "--name [^ ]+" | cut -d' ' -f2)
mkdir -p logs/bench
nohup /system/bin/setsid python -m bench.run_bench --root "$@" > "logs/bench/${name:-run}.out" 2>&1 < /dev/null &
echo "бенчмарк «${name:-run}» запущен в фоне, вывод: logs/bench/${name:-run}.out"
