#!/bin/bash
# Channel: docs quickstart — do the README's own commands work, run VERBATIM?
#
#   ./quickstart_check.sh [--out DIR]
#
# Two command blocks live in the README at the pinned tag (drift-checked here):
#   A. "Quick Try (No Code)": uv tool install litert-lm; litert-lm run
#      --from-huggingface-repo=google/gemma-3n-E2B-it-litert-lm gemma-3n-E2B-it-int4
#      --prompt=...            (gated repo, ~3.6GB — the full new-user path)
#   B. the header command: --from-huggingface-repo=litert-community/gemma-4-E2B-it-litert-lm
#      gemma-4-E4B-it.litertlm --backend=gpu --enable-speculative-decoding=true
#      (as of v0.16.1 the E4B FILE lives in the E4B repo — measured below)
#
# uv install is hermetic (UV_TOOL_DIR under cache/); model downloads land in the
# CLI's own cache. Non-interactive runs always get </dev/null (the CLI blocks
# forever on an inherited tty otherwise).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=""; [ "${1:-}" = "--out" ] && OUT="$2"
WORK="$HERE/cache/quickstart_work"
mkdir -p "$WORK"
TAG=$(grep '^GEN_LITERTLM_TAG=' "$HERE/pins.env" | cut -d= -f2)
GEN=$(grep '^GEN_PYPI_LITERT_LM=' "$HERE/pins.env" | cut -d= -f2)

# ---- 0. drift check: are the commands we hardcode still the documented ones?
gh api "repos/google-ai-edge/LiteRT-LM/contents/README.md?ref=$TAG" --jq .content 2>/dev/null \
  | base64 -d > "$WORK/README.md" || true
DRIFT="ok"
grep -q 'uv tool install litert-lm' "$WORK/README.md" || DRIFT="uv block missing"
grep -q -- '--from-huggingface-repo=google/gemma-3n-E2B-it-litert-lm' "$WORK/README.md" || DRIFT="gemma-3n cmd drifted"
grep -q -- '--from-huggingface-repo=litert-community/gemma-4-E2B-it-litert-lm' "$WORK/README.md" || DRIFT="gemma-4 cmd drifted"
grep -q 'gemma-4-E4B-it.litertlm' "$WORK/README.md" || DRIFT="gemma-4 file arg drifted"

# ---- 1. uv tool install litert-lm (hermetic)
export UV_TOOL_DIR="$WORK/uv-tools" UV_TOOL_BIN_DIR="$WORK/uv-bin"
rm -rf "$UV_TOOL_DIR" "$UV_TOOL_BIN_DIR"
uv tool install litert-lm > "$WORK/uv_install.log" 2>&1
UV_RC=$?
export PATH="$UV_TOOL_BIN_DIR:$PATH"
CLI_VER=$("$UV_TOOL_BIN_DIR/litert-lm" --version </dev/null 2>&1 | tr -d '\n' | tail -c 60 || true)
echo "[quickstart] uv install rc=$UV_RC version='$CLI_VER'"

# ---- 2. documented file really in the documented repo? (API-level, no download)
E4B_IN_E2B=$(python3 - <<'EOF'
import json, urllib.request
try:
    d = json.load(urllib.request.urlopen(
        "https://huggingface.co/api/models/litert-community/gemma-4-E2B-it-litert-lm", timeout=20))
    names = [s["rfilename"] for s in d.get("siblings", [])]
    print("yes" if "gemma-4-E4B-it.litertlm" in names else "no")
except Exception as e:
    print(f"api-error:{type(e).__name__}")
EOF
)
echo "[quickstart] gemma-4-E4B-it.litertlm in the documented (E2B) repo: $E4B_IN_E2B"

QT_RC=97; GF_RC=97
if [ $UV_RC -eq 0 ]; then
  # ---- 3. Quick Try, verbatim (gated google repo; full download on first run)
  ( litert-lm run \
      --from-huggingface-repo=google/gemma-3n-E2B-it-litert-lm \
      gemma-3n-E2B-it-int4 \
      --prompt="What is the capital of France?" \
      </dev/null > "$WORK/quicktry.log" 2>&1 )
  QT_RC=$?
  echo "[quickstart] quicktry rc=$QT_RC tail: $(tail -c 200 "$WORK/quicktry.log" | tr '\n' ' ')"

  # ---- 4. header command, verbatim (expected to fail fast if the file arg
  #         does not exist in the named repo; 10 min cap in case it downloads)
  ( litert-lm run  \
      --from-huggingface-repo=litert-community/gemma-4-E2B-it-litert-lm \
      gemma-4-E4B-it.litertlm \
      --backend=gpu \
      --enable-speculative-decoding=true \
      --prompt="What is the capital of France?" \
      </dev/null > "$WORK/gemma4_verbatim.log" 2>&1 ) &
  GPID=$!
  for _ in $(seq 1 600); do kill -0 "$GPID" 2>/dev/null || break; sleep 1; done
  if kill -0 "$GPID" 2>/dev/null; then kill "$GPID" 2>/dev/null; GF_RC=98; else wait "$GPID"; GF_RC=$?; fi
  echo "[quickstart] gemma-4 verbatim rc=$GF_RC tail: $(tail -c 200 "$WORK/gemma4_verbatim.log" | tr '\n' ' ')"

  # ---- 5. the same documented flow with a small UNGATED official model —
  #         separates "the uv->CLI->HF->generate pipe works" from "the two
  #         documented commands are gated/broken". Not a verbatim README run.
  #         (gemma-3-270m-it is gated=auto and the CLI sends no ambient token,
  #         so it 401s — measured 2026-08-31; granite-4.0-h-350m is gated=False.)
  ( litert-lm run \
      --from-huggingface-repo=litert-community/granite-4.0-h-350m \
      granite-4.0-h-350m_int8.litertlm \
      --prompt="What is the capital of France?" \
      </dev/null > "$WORK/swapped_e2e.log" 2>&1 ) &
  SPID=$!
  for _ in $(seq 1 1200); do kill -0 "$SPID" 2>/dev/null || break; sleep 1; done
  if kill -0 "$SPID" 2>/dev/null; then kill "$SPID" 2>/dev/null; SW_RC=98; else wait "$SPID"; SW_RC=$?; fi
  echo "[quickstart] swapped-model e2e rc=$SW_RC tail: $(tail -c 160 "$WORK/swapped_e2e.log" | tr '\n' ' ')"
fi

python3 - "$HERE" "$OUT" "$DRIFT" "$UV_RC" "$CLI_VER" "$GEN" "$E4B_IN_E2B" "$QT_RC" "$GF_RC" "$WORK" "${SW_RC:-97}" <<'EOF'
import os, re, sys
(here, out, drift, uv_rc, cli_ver, gen, e4b_in_e2b, qt_rc, gf_rc, work, sw_rc) = sys.argv[1:12]
sys.path.insert(0, here)
from channels_common import check, write_result
checks = []

checks.append(check(
    "quickstart.readme-drift",
    "hardcoded verbatim commands still match the README at the pinned tag",
    "PASS" if drift == "ok" else "FAIL",
    drift, issue="", evidence=f"{work}/README.md"))

ok_uv = uv_rc == "0" and gen in cli_ver
checks.append(check(
    "quickstart.uv-install",
    f"`uv tool install litert-lm` resolves to the generation ({gen})",
    "PASS" if ok_uv else "FAIL",
    f"rc={uv_rc}, litert-lm --version -> {cli_ver!r}",
    issue="", evidence=f"{work}/uv_install.log"))

def logtext(name):
    try:
        return open(os.path.join(work, name), errors="replace").read()
    except Exception:
        return ""

# Quick Try (gemma-3n, gated): distinguish auth-walls from channel defects
qt = logtext("quicktry.log")
gated = bool(re.search(r"401|403|unauthorized|gated|access.*request|forbidden", qt, re.I))
answered = bool(re.search(r"Paris", qt))
if qt_rc == "0" and answered:
    st, meas = "PASS", "generated (answer contains 'Paris')"
elif qt_rc == "0":
    st, meas = "FAIL", f"exit 0 but no answer text; tail: {qt[-160:]!r}"
elif gated:
    st, meas = "SKIP", f"blocked by gating/auth (user-side prerequisite): {qt[-140:]!r}"
elif qt_rc == "97":
    st, meas = "SKIP", "blocked: uv install failed"
else:
    st, meas = "FAIL", f"rc={qt_rc}; tail: {qt[-160:]!r}"
checks.append(check(
    "quickstart.quicktry-verbatim",
    "README Quick Try block, verbatim (uv CLI + google/gemma-3n-E2B-it-litert-lm)",
    st, meas, issue="", evidence=f"{work}/quicktry.log"))

# header command: the documented repo/file pairing itself
pair_ok = e4b_in_e2b == "yes"
checks.append(check(
    "quickstart.gemma4-cmd-file-exists",
    "README header cmd: file arg `gemma-4-E4B-it.litertlm` exists in the named (E2B) repo",
    "PASS" if pair_ok else "FAIL",
    f"in-repo={e4b_in_e2b}; the file exists in litert-community/gemma-4-E4B-it-litert-lm instead",
    issue="" if pair_ok else "LiteRT-LM#3418 (ours, posted 2026-08-31)",
    evidence="HF API model file listing"))

g4 = logtext("gemma4_verbatim.log")
if gf_rc == "97":
    st, meas = "SKIP", "blocked: uv install failed"
elif gf_rc == "98":
    st, meas = "FAIL", f"still running after 10min cap; tail: {g4[-140:]!r}"
elif gf_rc == "0" and re.search(r"Paris", g4):
    st, meas = "PASS", "generated (answer contains 'Paris')"
else:
    st, meas = "FAIL", f"rc={gf_rc}; tail: {g4[-180:]!r}"
checks.append(check(
    "quickstart.gemma4-cmd-verbatim",
    "README header command, verbatim (gpu + speculative decoding)",
    st, meas,
    issue="" if st == "PASS" else "LiteRT-LM#3418 (ours, posted 2026-08-31)",
    evidence=f"{work}/gemma4_verbatim.log"))

sw = logtext("swapped_e2e.log")
if sw_rc == "97":
    st, meas = "SKIP", "blocked: uv install failed"
elif sw_rc == "98":
    st, meas = "FAIL", f"still running after 20min cap; tail: {sw[-140:]!r}"
elif sw_rc == "0" and re.search(r"Paris", sw):
    st, meas = "PASS", "uv CLI + HF download + CPU generate all work (answer contains 'Paris')"
else:
    st, meas = "FAIL", f"rc={sw_rc}; tail: {sw[-160:]!r}"
checks.append(check(
    "quickstart.cli-hf-e2e-swapped-model",
    "documented flow with an ungated small model (litert-community/granite-4.0-h-350m) — "
    "isolates pipe health from the broken/gated documented commands",
    st, meas, issue="", evidence=f"{work}/swapped_e2e.log"))

write_result("quickstart", checks, out or None,
             extra={"cli_version": cli_ver, "drift": drift})
sys.exit(1 if any(c["status"] == "FAIL" for c in checks) else 0)
EOF
