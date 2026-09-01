#!/bin/bash
# Channel: npm — do the published web packages actually contain a runtime?
#
#   ./npm_check.sh [--out DIR]
#
# Checks, against whatever `latest` resolves to TODAY (recorded next to pins):
#   1. @litert-lm/core: tarball contents vs its own package.json `files` globs
#      (#3364: 0.16.0 ships only package.json), and version lag vs the GH tag.
#   2. @litertjs/core: dist/index.js + the 4 wasm builds present.
#   3. litert.js smoke: headless Chrome loads the PACKED package, compiles the
#      canary .tflite and runs one real inference (wasm accelerator).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=""; [ "${1:-}" = "--out" ] && OUT="$2"
WORK="$HERE/cache/npm_work"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
rm -rf "$WORK" && mkdir -p "$WORK"
cd "$WORK"

LM_VER=$(npm view @litert-lm/core version 2>/dev/null)
JS_VER=$(npm view @litertjs/core version 2>/dev/null)
echo "[npm] latest today: @litert-lm/core=$LM_VER @litertjs/core=$JS_VER"

npm pack "@litert-lm/core@$LM_VER" --silent >/dev/null 2>&1
npm pack "@litertjs/core@$JS_VER" --silent >/dev/null 2>&1
npm pack "@litertjs/wasm-utils" --silent >/dev/null 2>&1   # runtime dep of core
LM_TGZ=$(ls litert-lm-core-*.tgz 2>/dev/null | head -1)
JS_TGZ=$(ls litertjs-core-*.tgz 2>/dev/null | head -1)
WU_TGZ=$(ls litertjs-wasm-utils-*.tgz 2>/dev/null | head -1)

tar -tzf "$LM_TGZ" > lm_files.txt 2>/dev/null || true
tar -tzf "$JS_TGZ" > js_files.txt 2>/dev/null || true
LM_COUNT=$(wc -l < lm_files.txt | tr -d ' ')
LM_SIZE=$(stat -f%z "$LM_TGZ" 2>/dev/null || echo 0)

# litert.js: unpack and serve for the Chrome smoke
mkdir -p serve/litertjs serve/wasm-utils
tar -xzf "$JS_TGZ" -C serve/litertjs --strip-components=1
tar -xzf "$WU_TGZ" -C serve/wasm-utils --strip-components=1
# canary resolution shares the python helper (local -> hf-cache -> download)
CANARY=$(python3 - "$HERE" <<'EOF'
import sys, os
sys.path.insert(0, sys.argv[1])
from channels_common import load_pins, resolve_canary
p = load_pins()
path, src = resolve_canary(p["CANARY_TFLITE_REPO"], p["CANARY_TFLITE_FILE"],
                           p.get("CANARY_TFLITE_LOCAL"))
print(path)
EOF
)
cp "$CANARY" serve/canary.tflite
cp "$HERE/npm_smoke/smoke.html" serve/smoke.html

PORT=8973
python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$WORK/serve" >server.log 2>&1 &
SRV=$!
sleep 1
# Chrome headless=new sometimes lingers after --dump-dom has written the final
# DOM; poll for the RESULT marker and kill it rather than waiting on exit.
"$CHROME" --headless=new --disable-gpu --no-first-run --no-default-browser-check \
  --user-data-dir="$WORK/chrome-profile" --virtual-time-budget=45000 --timeout=90000 \
  --dump-dom "http://127.0.0.1:$PORT/smoke.html" > dom.txt 2>chrome.log &
CPID=$!
for _ in $(seq 1 120); do
  grep -q 'RESULT:' dom.txt 2>/dev/null && break
  kill -0 "$CPID" 2>/dev/null || break
  sleep 1
done
kill "$CPID" 2>/dev/null; wait "$CPID" 2>/dev/null
kill "$SRV" 2>/dev/null
SMOKE=$(grep -o 'RESULT:.*' dom.txt | head -1 | sed 's/^RESULT://' | sed 's/<[^>]*>.*//')
echo "[npm] smoke: ${SMOKE:-<no RESULT in DOM>}"

python3 - "$HERE" "$OUT" "$LM_VER" "$JS_VER" "$LM_COUNT" "$LM_SIZE" "$WORK" <<'EOF'
import json, os, sys
here, out, lm_ver, js_ver, lm_count, lm_size, work = sys.argv[1:8]
sys.path.insert(0, here)
from channels_common import check, load_pins, write_result
pins = load_pins()
checks = []

lm_files = [l.strip() for l in open(os.path.join(work, "lm_files.txt")) if l.strip()]
js_files = [l.strip() for l in open(os.path.join(work, "js_files.txt")) if l.strip()]

# --- @litert-lm/core: the package must contain what its own manifest declares
has_runtime = any(f.startswith("package/dist/") for f in lm_files)
has_wasm = any(f.startswith("package/wasm/") for f in lm_files)
checks.append(check(
    "npm.litert-lm-core.contents",
    "@litert-lm/core tarball contains dist/ + wasm/ (its package.json `files` globs)",
    "PASS" if (has_runtime and has_wasm) else "FAIL",
    f"v{lm_ver}: {len(lm_files)} file(s), {lm_size}B tarball: {lm_files[:3]}",
    issue="" if (has_runtime and has_wasm) else "LiteRT-LM#3364 (dup #9418 on LiteRT)",
    evidence="npm pack @litert-lm/core; tar -tzf"))

gen = pins["GEN_PYPI_LITERT_LM"]
checks.append(check(
    "npm.litert-lm-core.version-lag",
    f"npm latest vs the release generation ({gen})",
    "PASS" if lm_ver == gen else "FAIL",
    f"npm latest = {lm_ver}, GH/PyPI generation = {gen}",
    issue="" if lm_ver == gen else "LiteRT-LM#3364 (no fixed republish yet)",
    evidence="npm view @litert-lm/core version"))

# --- @litertjs/core: real runtime files present
wasm_builds = [f for f in js_files if f.endswith(".wasm")]
ok_js = "package/dist/index.js" in js_files and len(wasm_builds) >= 4
checks.append(check(
    "npm.litertjs-core.contents",
    "@litertjs/core contains dist/index.js + the wasm builds",
    "PASS" if ok_js else "FAIL",
    f"v{js_ver}: {len(js_files)} files, wasm builds: {len(wasm_builds)}",
    issue="",
    evidence="npm pack @litertjs/core; tar -tzf"))

# --- headless Chrome inference smoke
smoke_raw = ""
try:
    dom = open(os.path.join(work, "dom.txt")).read()
    import re
    m = re.search(r"RESULT:(\{.*?\})\s*<", dom, re.S) or re.search(r"RESULT:(\{.*\})", dom, re.S)
    smoke_raw = m.group(1) if m else ""
    smoke = json.loads(smoke_raw)
except Exception:
    smoke = None
if smoke and smoke.get("ok"):
    st, meas = "PASS", (f"canary inference ok on wasm, {smoke.get('infer_ms')}ms, "
                        f"outputs finite: {smoke.get('outputs')}")
elif smoke:
    st, meas = "FAIL", f"smoke returned ok=false: {str(smoke)[:200]}"
else:
    st, meas = "FAIL", "no RESULT parsed from headless Chrome DOM (see chrome.log/dom.txt)"
checks.append(check(
    "npm.litertjs-core.browser-smoke",
    "headless Chrome: loadLiteRt + loadAndCompile(canary.tflite) + run, outputs finite",
    st, meas, issue="",
    evidence=f"{work}/dom.txt"))

# --- @litert-lm/core smoke is blocked while the package is empty
if not (has_runtime and has_wasm):
    checks.append(check(
        "npm.litert-lm-core.browser-smoke",
        "web LLM smoke of @litert-lm/core",
        "SKIP", "blocked: package has no runtime files to load (see contents FAIL)",
        issue="LiteRT-LM#3364"))

write_result("npm", checks, out or None,
             extra={"npm_latest": {"@litert-lm/core": lm_ver, "@litertjs/core": js_ver}})
sys.exit(1 if any(c["status"] == "FAIL" for c in checks) else 0)
EOF
