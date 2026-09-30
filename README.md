# 🍋 Lemonade Agent

**An AI agent that operates a real Android phone on its own.** It looks at the screen, decides what to tap, and taps.
Named after the OnePlus 9 codename — *lemonade*.

This is an open research project. The plan: build a phone agent, benchmark it, make it learn from its own
experience, distill it into a small model that runs **offline on the phone**, and stress-test it against
prompt injections that come from the screen.

🇷🇺 [Русская версия](README.ru.md)

> **Status:** Stage 1. The agent drives the phone from a PC over USB (adb); the brain is DeepSeek `deepseek-flash`.
> Follow the progress in the [devlog](docs/devlog.md) (in Russian).

## How it works

```
task ──► observe ──► decide ──► safety check ──► act ──► … until "done"
            │           │             │             │
     UI tree +     DeepSeek:     risky taps →   adb input
     numbered      one JSON      human confirms tap / text / swipe
     screenshot    action
```

This is what the model actually sees on the Settings → Display screen (the phone UI and the prompt are in Russian):

```
Приложение: com.android.settings                  ← "App:"
[4] LinearLayout "Светлый режим" {click}          ← "Light mode"
[5] RadioButton id=rb_light_button {off}
[6] LinearLayout "Режим затемнения" {click}       ← "Dark mode"
[7] RadioButton id=rb_dark_button {on}
```

It also gets a screenshot where the same elements are boxed and numbered (Set-of-Mark), and it answers with a
single action (the thought is translated from Russian):

```json
{"thought": "Dark mode is on, the task asks for light mode — tap it", "action": "tap", "id": 4}
```

| Layer | File | What it does |
|---|---|---|
| Device | [`agent/device.py`](agent/device.py) | One interface, two backends: `AdbDevice` (PC over USB) and `RootDevice` (on the phone via `su`) |
| Perception | [`agent/perception.py`](agent/perception.py) | `uiautomator dump` → compact numbered list; screenshot → downscaled JPEG with the same numbers |
| Brain | [`agent/brain.py`](agent/brain.py) | DeepSeek through the OpenAI-compatible API, one JSON action per step |
| Safety | [`agent/safety.py`](agent/safety.py) | Taps on "Send / Pay / Delete…" need human confirmation; banking and wallet apps are blocked |
| Loop | [`agent/loop.py`](agent/loop.py) | observe → decide → act; notices when the screen didn't change; logs every step |

Every run is saved to `logs/`: raw screenshots, the UI tree, what the model saw and what it answered.
That is both material for videos and a "screen → action" dataset for training a small local model later.

## First results

Checked against the real system state (e.g. `cmd uimode night`), not just the agent's own claim.

| Task | Result | Steps | Time |
|---|---|---|---|
| Turn on light theme | ✅ 2/2 | 4–5 | 19–24 s |
| Turn on dark theme | ✅ 3/3 | 6–9 | 32–48 s |
| Type «яркость» (Cyrillic) into Settings search | ✅ 1/1 | 3 | 17 s |
| Find the weather in the browser | ✅ 1/1 | 18 | 130 s |
| Search Google for «лимонад» | ✅ 1/1 | 4 | 24 s |
| Set an alarm for 7:00 | ✅ 1/1 | 3 | 15 s |
| Turn off the 7:00 alarm without deleting it | ✅ 1/1 | 5 | 25 s |

The same task takes anywhere from 4 to 9 steps because the agent rediscovers where the setting lives every time.
That's exactly what skill memory (Stage 4) is supposed to fix, and it's the baseline for the learning curve.
The weather run took 18 steps because of two bugs it exposed (the keyboard covering the results and the model's
reasoning eating the whole token budget); both are fixed, and the next browser search took 4 steps.

## Quick start

You need Python 3.10+, [adb](https://developer.android.com/tools/releases/platform-tools), an Android phone with
USB debugging on, and a [DeepSeek API key](https://platform.deepseek.com/).

> ⚠️ Use a spare phone with a test account: screenshots are sent to the DeepSeek API.

```bash
git clone https://github.com/shyqzax/LemonadeAgent.git
cd LemonadeAgent
python -m venv .venv
.venv\Scripts\activate           # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # then put your DeepSeek key into .env
python scripts/doctor.py         # checks the phone, the key and scrcpy
python -m interfaces.cli "turn on dark theme"
```

Options: `--mode both|tree|screen` (what the model sees), `--max-steps N`, `--serial SERIAL`. Stop at any time with `Ctrl+C`.

Typing non-Latin text needs [ADBKeyBoard](https://github.com/senzhk/ADBKeyBoard) (`adb install` its APK).
The agent switches to it only while typing and then restores your keyboard.

## Roadmap

- [x] **Stage 0.** Setup: adb, scrcpy, DeepSeek
- [x] **Stage 1.** First agent, driven from a PC, no root
- [ ] **Stage 2.** Unlock the bootloader, LineageOS 23 (Android 16), root
- [ ] **Stage 3.** The agent lives on the phone (Termux + root) and takes commands from a Telegram bot
- [ ] **Stage 4.** Benchmark (~30 auto-checked tasks) + skill memory → learning curve
- [ ] **Stage 5.** Local brain: a small model in llama.cpp on the Snapdragon 888, distilled from DeepSeek runs
- [ ] **Stage 6.** Security: prompt injections from the screen, attack set, block rate before/after defenses
- [ ] **Stage 7.** Write-ups and videos

The full research plan (in Russian) is in [docs/PLAN.md](docs/PLAN.md).

## Safety

- A spare phone with a separate Google account: no banks, no main messengers.
- Taps on buttons like "Send", "Pay", "Delete" require confirmation from a human.
- Banking, wallet and crypto apps are blocked.
- Step limit and `Ctrl+C` as a kill switch.
- The prompt tells the model that text on the screen is data, not instructions. How well that holds up is what Stage 6 will measure.

## License

[MIT](LICENSE)
