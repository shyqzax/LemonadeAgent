# 🍋 Lemonade Agent

**An AI agent that operates a real Android phone on its own.** It looks at the screen, decides what to tap, and taps.
Named after the OnePlus 9 codename — *lemonade*.

This is an open research project. The plan: build a phone agent, benchmark it, make it learn from its own
experience, distill it into a small model that runs **offline on the phone**, and stress-test it against
prompt injections that come from the screen.

🇷🇺 [Русская версия](README.ru.md)

> **Status:** Stage 4 done. The agent lives on the phone itself (Termux + root, LineageOS 23.2 / Android 16),
> takes tasks from a Telegram bot, and learns from experience: on a 30-task benchmark, skill memory cuts model calls
> by 30%. The brain is DeepSeek `deepseek-flash` for now; a small on-device model is Stage 5.
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

## Benchmark: does the agent learn from experience?

30 tasks — settings toggles, alarms, calculator, contacts, browser, questions about the phone, a few multi-app ones.
Before each task the phone is reset to the same starting state, and success is **checked against the real system
state** (`settings get`, `dumpsys alarm`, `content query`…), not the agent's own claim. Each experiment runs every
task 3 rounds: with skill memory, and a control without it.

![Learning curve](docs/img/learning_curve.svg)

| Rounds 2–3 (memory already has experience) | With memory | No memory |
|---|---|---|
| **Model calls per task** | **5.3** | 7.6 |
| Cost of 60 tasks | **$0.147** | $0.171 |
| Success | 58/60 | 57/60 |
| Time per task | 52 s | 51 s |

**How the memory works.** A successful, verified run is saved as a human-readable skill
(`open_app settings → tap «Display» → tap «Dark theme»`). When the exact same task comes again, the agent **replays
the known path by itself, finding buttons by their labels — no model calls**. The last, decisive step is left to the
model, because the state may differ (blindly replaying "turn on Bluetooth" when it's already on would turn it off).
For similar tasks the skill goes into the prompt as a hint.

What we found:
- **Replay cuts model calls by 30% and cost by 14% with no loss in success.** Where replay kicked in, 51/51 tasks
  succeeded. The biggest wins are on long tasks: "compute 3 + 4 and set an alarm for that hour" took 2 model calls
  instead of 16 and 47 s instead of 101 s.
- **Time barely improved** — the model isn't the bottleneck. Reading the screen (`uiautomator dump`) takes ~2.3 s
  per step whether the model thinks or not.
- **The first version of memory — hints in the prompt only — gave nothing** (7.7 steps either way, and slightly more
  expensive because of the longer prompt). Analysing it surfaced two bugs in the benchmark itself and one in the agent's
  typing tool; all fixed. Details in the [devlog](docs/devlog.md).
- One honest failure remains: "restore the default font size". On Android 16 the slider has 7 positions and the
  default is the second one; the agent reasons like a human — "default = middle" — and confidently reports success.

A full round of 30 tasks costs about **$0.06–0.10** with `deepseek-flash`.

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

Run the benchmark (from the PC over adb; add `--root` to run it on the phone itself):

```bash
python -m bench.run_bench --rounds 3 --memory --name memory
python -m bench.run_bench --rounds 3 --name baseline
python scripts/plot_bench.py memory baseline     # → docs/img/learning_curve.svg
```

Typing non-Latin text needs [ADBKeyBoard](https://github.com/senzhk/ADBKeyBoard) (`adb install` its APK).
The agent switches to it only while typing and then restores your keyboard.

## Roadmap

- [x] **Stage 0.** Setup: adb, scrcpy, DeepSeek
- [x] **Stage 1.** First agent, driven from a PC, no root
- [x] **Stage 2.** Unlock the bootloader, LineageOS 23.2 (Android 16), root with Magisk. The same agent worked on the new OS with zero code changes
- [x] **Stage 3.** The agent lives on the phone (Termux + root), takes tasks from a Telegram bot, asks for confirmation via buttons and starts on boot
- [x] **Stage 4.** Benchmark (30 auto-checked tasks) + skill memory with replay → 30% fewer model calls
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
