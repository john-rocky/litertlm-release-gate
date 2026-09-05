#!/usr/bin/env python3
"""Diff two release-artifact-gate runs by check id.

    python3 watch/on_release/channels/diff_tables.py \
        reports/release_artifact_gate_20260831_data reports/release_artifact_gate_20260906_data

Prints four lists — FAIL->PASS (fix confirmed, comment seed), PASS->FAIL (release
regression), NEW checks, GONE checks — plus the unchanged count. Status changes
are what a follow-up message is made of; an unchanged FAIL is not news.
"""
import glob
import json
import os
import sys


def load(data_dir):
    rows = {}
    for p in glob.glob(os.path.join(data_dir, "*.json")):
        d = json.load(open(p))
        if "checks" not in d:
            continue
        for c in d["checks"]:
            rows[c["id"]] = (c["status"], c.get("measured", ""), c.get("issue", ""))
    return rows


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a, b = load(sys.argv[1]), load(sys.argv[2])
    fixed, regressed, changed, new, gone, same = [], [], [], [], [], 0
    for cid in sorted(set(a) | set(b)):
        if cid not in a:
            new.append((cid, b[cid]))
        elif cid not in b:
            gone.append((cid, a[cid]))
        elif a[cid][0] != b[cid][0]:
            sa, sb = a[cid][0], b[cid][0]
            if sa == "FAIL" and sb == "PASS":
                fixed.append((cid, a[cid], b[cid]))
            elif sa == "PASS" and sb == "FAIL":
                regressed.append((cid, a[cid], b[cid]))
            else:
                changed.append((cid, a[cid], b[cid]))
        else:
            same += 1

    def show(title, items):
        print(f"\n## {title} ({len(items)})")
        for it in items:
            cid = it[0]
            if len(it) == 3:
                print(f"- `{cid}`: {it[1][0]} -> {it[2][0]}  | before: {it[1][1][:90]} | after: {it[2][1][:90]}"
                      + (f" | issue: {it[1][2] or it[2][2]}" if (it[1][2] or it[2][2]) else ""))
            else:
                print(f"- `{cid}`: {it[1][0]} | {it[1][1][:110]}" + (f" | issue: {it[1][2]}" if it[1][2] else ""))

    print(f"# gate diff: {os.path.basename(sys.argv[1])} -> {os.path.basename(sys.argv[2])}")
    print(f"checks before {len(a)} / after {len(b)} / unchanged {same}")
    show("FAIL -> PASS (fix confirmed — comment seed)", fixed)
    show("PASS -> FAIL (release regression)", regressed)
    show("other status change (SKIP involved)", changed)
    show("NEW checks", new)
    show("GONE checks", gone)
    return 0


if __name__ == "__main__":
    sys.exit(main())
