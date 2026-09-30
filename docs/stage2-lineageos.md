# Этап 2: разблокировка, LineageOS 23.2 и Google-сервисы

> ✅ Выполнено 2026-10-01. Что пошло не по плану и как обходили — в [devlog](devlog.md).

Источник — только официальная вики, сверено 2026-10-01:
- устройство: https://wiki.lineageos.org/devices/lemonade/variant1/
- установка: https://wiki.lineageos.org/devices/lemonade/install/variant1/
- Google Apps: https://wiki.lineageos.org/gapps/

👤 — делает владелец руками, 🤖 — делает Claude командами с ПК.

## Что известно о телефоне

| | |
|---|---|
| Модель | **LE2111** — есть в списке поддерживаемых (LE2110 / LE2111 / LE2113 / LE2115) |
| Прошивка | OxygenOS `LE2111_14.0.0.1902(EX01)`, Android 14, патч 2025-04-01 |
| Требование вики | стоковая прошивка **Android 13/14**, причём последнее обновление этой версии |
| Загрузчик | заблокирован, «Разблокировка OEM» включена |
| Вход в fastboot кнопками | на выключенном телефоне зажать **Громкость+ + Громкость− + Питание** |

## Перед началом (👤)

1. **Сохранить всё нужное** — разблокировка стирает телефон полностью.
2. **Обновить OxygenOS до последней версии Android 14**, если в «Обновление ПО» что-то предлагается. Вики требует последнюю
   сборку нужной версии Android. OnePlus 9 не получал Android 15, так что обновление будет в пределах 14.
3. **Проверить звонки и SMS**, если в телефоне будет SIM: на стоке один раз должны заработать VoLTE/VoWiFi.
4. **Удалить Google-аккаунт** из «Настройки → Аккаунты», иначе после сброса сработает защита от кражи (FRP).
5. Зарядить телефон минимум до 60%.

## Файлы (🤖 скачивает после согласия, сверяет SHA256)

| Файл | Откуда | Размер |
|---|---|---|
| `lineage-23.2-<дата>-nightly-lemonade-signed.zip` | download.lineageos.org/devices/lemonade | ~1,7 ГБ |
| `boot.img` (это Lineage Recovery) | там же, та же сборка | ~200 МБ |
| `dtbo.img`, `vbmeta.img`, `vendor_boot.img` | там же, та же сборка | ~230 МБ |
| `MindTheGapps-16.0.0-arm64-<дата>.zip` | github.com/MindTheGapps/16.0.0-arm64 | ~510 МБ |

Складываем в `tools/lineage/` (в git не попадает).

## Шаги

1. 🤖 `adb -d reboot bootloader` → `fastboot devices`. Если Windows не видит телефон в fastboot — ставим драйвер.
2. 🤖 `fastboot oem unlock` → 👤 подтверждаешь на экране телефона кнопками громкости и питанием. **Все данные стираются.**
3. 👤 Телефон перезагружается в OxygenOS с нуля. Снова заходим в fastboot кнопками (Громкость+ + Громкость− + Питание).
4. 🤖 Дополнительные разделы:
   ```
   fastboot flash dtbo dtbo.img
   fastboot flash vbmeta vbmeta.img
   fastboot flash vendor_boot vendor_boot.img
   fastboot reboot bootloader
   ```
5. 🤖 Lineage Recovery: `fastboot flash boot boot.img`. 👤 Кнопками громкости выбираешь **Recovery** и жмёшь питание.
   Должен быть логотип LineageOS, иначе начать шаг заново.
6. 👤 В recovery: **Factory Reset → Format data / factory reset**, потом назад в главное меню.
7. 👤 **Apply update → Apply from ADB**. 🤖 `adb -d sideload lineage-23.2-…zip`.
   Остановка на 47% с `adb: failed to read command: Success` — это нормально.
8. 👤 На вопрос про перезагрузку в recovery для дополнений отвечаешь **Yes**.
9. 👤 **Apply update → Apply from ADB**. 🤖 `adb -d sideload MindTheGapps-…zip`.
   👤 На «Signature verification failed» — **Yes** (дополнения не подписаны ключом LineageOS, это ожидаемо).
   Gapps ставятся **до** первой загрузки системы, иначе придётся начинать заново.
10. 👤 Стрелка назад → **Reboot system now**. Первая загрузка — до 15 минут.
11. 👤 Мастер настройки, **новый тестовый** Google-аккаунт, снова «Для разработчиков» → «Отладка по USB».

## После (отдельные шаги)

- Root через Magisk или KernelSU-Next — LineageOS его официально не поддерживает, делаем отдельно.
- ADBKeyBoard **v2.5** (в ней исправление под Android 16).
- Проверка: `adb shell su -c id` → `uid=0`, Play Маркет работает, агент проходит задачи этапа 1 на новой системе.

## Если что-то пошло не так

- Ничего не делаем «по памяти». Если шаг упал — стоп, разбираемся, не переходим к следующему.
- Последний рубеж — OnePlus MSM Download Tool (EDL): восстанавливает сток почти из любого «кирпича».
