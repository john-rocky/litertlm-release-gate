#!/usr/bin/env python3
"""Merge the channel-runner JSONs into the one PASS/FAIL table.

    python3 ./make_table.py                # today's results
    python3 ./make_table.py --results DIR --no-copy

Writes reports/release_artifact_gate_<date>.md and copies the row JSONs into
reports/release_artifact_gate_<date>_data/ so the table's evidence survives the
gitignored results_*/ dir. A FAIL row without an `issue` is surfaced loudly as a
candidate NEW finding — those stay drafts until the user says GO.

If qa/out/compat_<GEN>.json exists (the standing PyPI-channel gate), a PyPI row
is synthesized from it rather than re-measured here.
"""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from channels_common import REPO, load_pins  # noqa: E402  (REPO = this repo)

ORDER = ["npm", "maven", "gh_assets", "swiftpm", "quickstart"]
LABEL = {"npm": "npm", "maven": "Maven (Android AAR)", "gh_assets": "GH release assets",
         "swiftpm": "SwiftPM (macOS)", "quickstart": "docs quickstart"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", help="results dir (default channels/results_<today>)")
    ap.add_argument("--report", help="output md (default reports/release_artifact_gate_<date>.md)")
    ap.add_argument("--no-copy", action="store_true", help="skip the _data/ evidence copy")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    date = time.strftime("%Y%m%d")
    rdir = args.results or os.path.join(here, f"results_{date}")
    pins = load_pins()
    gen = pins["GEN_LITERTLM_TAG"]

    rows = {}
    for p in glob.glob(os.path.join(rdir, "*.json")):
        d = json.load(open(p))
        if "channel" in d:
            rows[d["channel"]] = d
    if not rows:
        print(f"no channel results in {rdir}", file=sys.stderr)
        return 2

    report = args.report or os.path.join(REPO, "results", f"release_artifact_gate_{date}.md")
    os.makedirs(os.path.dirname(report), exist_ok=True)
    total = fails = news = 0
    lines = []
    lines.append(f"# リリース成果物ゲート 第0回 — {gen} 世代 ({time.strftime('%Y-%m-%d')})\n")
    lines.append("公開された配布物がチャネルごとに「実際にインストールできて動くか」の実測表。ハーネスは `./`(各行 re-run 可能、ピンは `pins.env`)。性能ベンチとは別軸 = 配布物の完全性。\n")
    lines.append(f"世代ピン: LiteRT-LM `{gen}` / LiteRT `{pins['GEN_LITERT_TAG']}` / PyPI `{pins['GEN_PYPI_LITERT_LM']}` / Maven `{pins['GEN_MAVEN_LITERTLM_ANDROID']}` / npm `@litert-lm/core {pins['GEN_NPM_LITERTLM_CORE']}` `@litertjs/core {pins['GEN_NPM_LITERTJS_CORE']}`。LLM canary: `{pins['CANARY_LLM_REPO']}/{pins['CANARY_LLM_FILE']}`。\n")
    lines.append("| チャネル | 検査 | 結果 | 実測 | 該当 issue |")
    lines.append("|---|---|---|---|---|")
    for ch in ORDER:
        if ch not in rows:
            continue
        for c in rows[ch]["checks"]:
            total += 1
            st = c["status"]
            if st == "FAIL":
                fails += 1
                if not c["issue"]:
                    news += 1
            mark = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "SKIP": "⏭ SKIP"}[st]
            issue = c["issue"] or ("**新規 — 草案のみ**" if st == "FAIL" else "—")
            meas = c["measured"].replace("|", "\\|").replace("\n", " ")[:170]
            lines.append(f"| {LABEL[ch]} | `{c['id']}` | {mark} | {meas} | {issue} |")
    lines.append("")
    lines.append(f"**{total} 検査 / {fails} FAIL(うち既知 issue 対応 {fails - news}・新規候補 {news})**\n")

    lines.append("## FAIL の note\n")
    for ch in ORDER:
        if ch not in rows:
            continue
        for c in rows[ch]["checks"]:
            if c["status"] != "FAIL":
                continue
            lines.append(f"- `{c['id']}` — {c['desc']}。実測: {c['measured']}。"
                         + (f"既知: {c['issue']}。" if c["issue"] else "**既知 issue なし → 草案止まり(投稿は user GO)**。")
                         + (f" 一次ログ: `{c['evidence']}`" if c.get("evidence") else ""))
    lines.append("")

    notes = os.path.join(rdir, "NOTES.md")
    if os.path.exists(notes):
        lines.append(open(notes).read().rstrip() + "\n")

    if not args.no_copy:
        data_dir = report[:-3] + "_data"
        os.makedirs(data_dir, exist_ok=True)
        for ch, d in rows.items():
            with open(os.path.join(data_dir, f"{ch}.json"), "w") as f:
                json.dump(d, f, indent=1)
        # drafts, notes and preserved evidence logs must survive the gitignored
        # results dir — they are the part of the run a future reader needs
        import shutil
        for pat in ("DRAFT_*.md", "NOTES.md", "*_evidence.log"):
            for src in glob.glob(os.path.join(rdir, pat)):
                shutil.copy2(src, data_dir)
        lines.append(f"行 JSON(検査の生データ): `{os.path.relpath(data_dir, REPO)}/`。"
                     f"一次ログは `./cache/` と results dir(gitignore、ローカル保持)。\n")

    with open(report, "w") as f:
        f.write("\n".join(lines))
    print(f"table: {report}  ({total} checks, {fails} FAIL, {news} new-candidate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
