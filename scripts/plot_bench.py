"""Кривая обучения: успех, шаги и стоимость по раундам бенчмарка — три графика рядом (одна ось на график).

    python scripts/plot_bench.py memory baseline --pull     # забрать результаты с телефона и построить
    python scripts/plot_bench.py memory                     # из уже скачанных logs/bench/<имя>/results.jsonl

Пишет docs/img/learning_curve.svg (подписи на английском, для README) и learning_curve_ru.svg (для README.ru).
SVG статичный (на GitHub он показывается как картинка), тёмная тема — через prefers-color-scheme внутри SVG.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHONE = "/data/data/com.termux/files/home/LemonadeAgent/logs/bench"

# эталонная палитра навыка dataviz: слоты 1–2 категориальной темы, светлая и тёмная ступени
SERIES = [("#2a78d6", "#3987e5"), ("#eb6834", "#d95926")]
TEXT = {
    "en": {"success": "Success, %", "calls": "Model calls per task", "cost": "Cost per round, ¢", "round": "round",
           "title": "Learning curve: {n} tasks per round"},
    "ru": {"success": "Успех, %", "calls": "Вызовов модели на задачу", "cost": "Стоимость раунда, ¢", "round": "раунд",
           "title": "Кривая обучения: {n} задач за раунд"},
}


def label(name: str, lang: str) -> str:
    if name.startswith("memory"):
        return "with memory" if lang == "en" else "с памятью"
    if name.startswith("baseline"):
        return "no memory" if lang == "en" else "без памяти"
    return name


def pull(name: str):
    local = ROOT / "logs" / "bench" / name
    local.mkdir(parents=True, exist_ok=True)
    for f in ("results.jsonl", "summary.md"):
        data = subprocess.run(["adb", "exec-out", f"su -c 'cat {PHONE}/{name}/{f}'"], capture_output=True).stdout
        if data:
            (local / f).write_bytes(data)
    print(f"забрал {name}: {(local / 'results.jsonl').stat().st_size} байт")


def per_round(name: str) -> tuple[list[dict], int]:
    rows = [json.loads(line) for line in (ROOT / "logs" / "bench" / name / "results.jsonl").read_text("utf-8").splitlines()
            if line.strip()]
    out, n_tasks = [], 0
    for rnd in sorted({r["round"] for r in rows}):
        rs = [r for r in rows if r["round"] == rnd]
        n_tasks = max(n_tasks, len(rs))
        # в первом эксперименте вызовов модели не считали — там каждый шаг был вызовом
        out.append({"round": rnd, "success": 100 * sum(r["success"] for r in rs) / len(rs),
                    "calls": sum(r.get("llm_calls", r["steps"]) for r in rs) / len(rs),
                    "cost": 100 * sum(r["cost_usd"] for r in rs)})
    return out, n_tasks


def svg(series: list[tuple[str, list[dict]]], n_tasks: int, lang: str) -> str:
    t = TEXT[lang]
    W, H, pad, gap = 960, 330, 24, 28
    pw = (W - 2 * pad - 2 * gap) / 3
    top, bottom = 96, H - 44
    rounds = sorted({p["round"] for _, pts in series for p in pts})
    css_vars = [f"--s{i + 1}:{light}" for i, (light, _) in enumerate(SERIES)]
    css_dark = [f"--s{i + 1}:{dark}" for i, (_, dark) in enumerate(SERIES)]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="system-ui, -apple-system, Segoe UI, sans-serif">',
           "<style>",
           f":root{{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;{';'.join(css_vars)}}}",
           f"@media (prefers-color-scheme: dark){{:root{{--bg:#1a1a19;--ink:#ffffff;--ink2:#c3c2b7;--muted:#898781;"
           f"--grid:#2c2c2a;--axis:#383835;{';'.join(css_dark)}}}}}",
           ".t{fill:var(--ink);font-size:16px;font-weight:600}.h{fill:var(--ink);font-size:13px;font-weight:600}"
           ".l{fill:var(--ink2);font-size:12px}.m{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}",
           "</style>",
           f'<rect width="{W}" height="{H}" rx="8" fill="var(--bg)"/>',
           f'<text class="t" x="{pad}" y="32">{t["title"].format(n=n_tasks)}</text>']
    # легенда — одна строка над графиками
    x = pad
    for i, (name, _) in enumerate(series):
        text = label(name, lang)
        out.append(f'<line x1="{x}" y1="56" x2="{x + 18}" y2="56" stroke="var(--s{i + 1})" stroke-width="2"/>'
                   f'<circle cx="{x + 9}" cy="56" r="4" fill="var(--s{i + 1})" stroke="var(--bg)" stroke-width="2"/>'
                   f'<text class="l" x="{x + 26}" y="60">{text}</text>')
        x += 40 + 8 * len(text)

    for k, (key, fmt) in enumerate((("success", "{:.0f}"), ("calls", "{:.1f}"), ("cost", "{:.1f}"))):
        x0 = pad + k * (pw + gap)
        left, right = x0 + 34, x0 + pw - 40  # слева — цифры оси, справа — подписи концов линий
        vals = [p[key] for _, pts in series for p in pts]
        ymax = 100 if key == "success" else max(vals) * 1.25 or 1
        sx = lambda r: left + 12 + (right - left - 24) * ((r - rounds[0]) / max(1, rounds[-1] - rounds[0]))  # noqa: E731
        sy = lambda v: bottom - (bottom - top) * v / ymax  # noqa: E731
        out.append(f'<text class="h" x="{x0}" y="{top - 14}">{t[key]}</text>')
        for g in range(5):  # тонкая сетка и подписи оси
            v = ymax * g / 4
            out.append(f'<line x1="{left}" y1="{sy(v):.1f}" x2="{right}" y2="{sy(v):.1f}" '
                       f'stroke="var({"--axis" if g == 0 else "--grid"})" stroke-width="1"/>'
                       f'<text class="m" x="{left - 6}" y="{sy(v) + 4:.1f}" text-anchor="end">{fmt.format(v)}</text>')
        for r in rounds:
            out.append(f'<text class="m" x="{sx(r):.1f}" y="{bottom + 18}" text-anchor="middle">{t["round"]} {r}</text>')
        # подписи концов линий: если оказываются ближе 14 px по вертикали — раздвигаем
        ends = sorted(((sy(pts[-1][key]), i, pts[-1][key]) for i, (_, pts) in enumerate(series)), key=lambda e: e[0])
        for j in range(1, len(ends)):
            if ends[j][0] - ends[j - 1][0] < 14:
                ends[j] = (ends[j - 1][0] + 14, ends[j][1], ends[j][2])
        for y, i, v in ends:
            out.append(f'<text class="l" x="{right + 6}" y="{y + 4:.1f}">{fmt.format(v)}</text>')
        for i, (_, pts) in enumerate(series):
            path = " ".join(f"{'M' if j == 0 else 'L'}{sx(p['round']):.1f},{sy(p[key]):.1f}" for j, p in enumerate(pts))
            out.append(f'<path d="{path}" fill="none" stroke="var(--s{i + 1})" stroke-width="2" '
                       f'stroke-linejoin="round" stroke-linecap="round"/>')
            for p in pts:
                out.append(f'<circle cx="{sx(p["round"]):.1f}" cy="{sy(p[key]):.1f}" r="4" fill="var(--s{i + 1})" '
                           f'stroke="var(--bg)" stroke-width="2"><title>{t["round"]} {p["round"]}: '
                           f'{fmt.format(p[key])}</title></circle>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Кривая обучения по результатам бенчмарка")
    p.add_argument("names", nargs="+", help="имена прогонов (logs/bench/<имя>), первый — главный")
    p.add_argument("--pull", action="store_true", help="сначала забрать результаты с телефона")
    args = p.parse_args()
    if args.pull:
        for n in args.names:
            pull(n)
    series, n_tasks = [], 0
    for n in args.names:
        pts, nt = per_round(n)
        series.append((n, pts))
        n_tasks = max(n_tasks, nt)
    img = ROOT / "docs" / "img"
    img.mkdir(parents=True, exist_ok=True)
    for lang, fname in (("en", "learning_curve.svg"), ("ru", "learning_curve_ru.svg")):
        (img / fname).write_text(svg(series, n_tasks, lang), encoding="utf-8")
        print(f"готово: docs/img/{fname}")


if __name__ == "__main__":
    main()
