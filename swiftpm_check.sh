#!/bin/bash
# Channel: SwiftPM — can a user `swift build` against the official package and generate?
#
#   ./swiftpm_check.sh [--out DIR]
#
#   1. resolve: `.package(url: google-ai-edge/LiteRT-LM, exact: <GEN minus v>)`.
#      If semver resolution of the v-prefixed tag fails, retry pinned to the tag
#      revision — the retry keeps measuring the build while the resolution
#      failure stays on the table as its own row.
#   2. build:   swift build -c release (pulls the pinned xcframework zips).
#   3. run:     one generate on the LLM canary; PASS = exit 0 + non-empty OUTPUT.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=""; [ "${1:-}" = "--out" ] && OUT="$2"
WORK="$HERE/cache/swiftpm_work"

VER=$(grep '^GEN_LITERTLM_TAG=' "$HERE/pins.env" | cut -d= -f2 | sed 's/^v//')
rm -rf "$WORK" && mkdir -p "$WORK"
cp -R "$HERE/swiftpm_client/Sources" "$WORK/"
sed -e "s/@LITERTLM_VERSION@/$VER/" -e "s/@LITERTLM_DEP@/exact: \"$VER\"/" \
  "$HERE/swiftpm_client/Package.swift.in" > "$WORK/Package.swift"
cd "$WORK"

RESOLVE_MODE="exact:$VER"
swift package resolve > resolve.log 2>&1
RES_RC=$?
# Separate the three distinct failure surfaces this channel has shown:
#   semver: can SwiftPM map exact:"0.16.1" onto the v-prefixed tag at all
#   lfs:    checkout smudge — SwiftPM checks out from its LOCAL bare mirror, so
#           git-lfs asks a path with no LFS endpoint and dies (#2407); the
#           object itself exists on GitHub's LFS (batch API verified 2026-08-31)
SEMVER_OK=0; grep -q "Computed .* at $VER" resolve.log && SEMVER_OK=1
LFS_FAIL=0; grep -q "smudge filter lfs failed" resolve.log && LFS_FAIL=1
if [ $RES_RC -ne 0 ] && [ "$LFS_FAIL" = "1" ]; then
  # workaround-mode so build/generate still get measured; the checkout FAIL
  # stays on the table regardless
  export GIT_LFS_SKIP_SMUDGE=1
  RESOLVE_MODE="exact:$VER +GIT_LFS_SKIP_SMUDGE=1"
  swift package resolve > resolve_skiplfs.log 2>&1
  RES_RC=$?
elif [ $RES_RC -ne 0 ] && [ "$SEMVER_OK" = "0" ]; then
  # true semver failure: pin the tag's commit as a revision instead
  SHA=$(gh api "repos/google-ai-edge/LiteRT-LM/commits/v$VER" --jq .sha 2>/dev/null)
  if [ -n "$SHA" ]; then
    sed -e "s/@LITERTLM_VERSION@/$VER/" -e "s/@LITERTLM_DEP@/revision: \"$SHA\"/" \
      "$HERE/swiftpm_client/Package.swift.in" > "$WORK/Package.swift"
    swift package resolve > resolve_revision.log 2>&1 && RESOLVE_MODE="revision:$SHA (exact FAILED)"
  fi
fi
RESOLVED=$(swift package show-dependencies 2>/dev/null | grep -i litert | head -1 | sed 's/^ *//')

swift build -c release > build.log 2>&1
BUILD_RC=$?
tail -3 build.log

RUN_RC=2; OUTPUT_LINE=""; INIT_LINE=""
if [ $BUILD_RC -eq 0 ]; then
  CANARY=$(python3 - "$HERE" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
from channels_common import load_pins, resolve_canary
p = load_pins()
path, src = resolve_canary(p["CANARY_LLM_REPO"], p["CANARY_LLM_FILE"])
print(path)
EOF
)
  ./.build/release/relgate "$CANARY" </dev/null > run.log 2>&1
  RUN_RC=$?
  OUTPUT_LINE=$(grep -m1 '^OUTPUT:' run.log || true)
  INIT_LINE=$(grep -m1 '^INIT_OK' run.log || true)
  FAILED_LINE=$(grep -m1 '^FAILED:' run.log || true)
  echo "[swiftpm] $INIT_LINE ${OUTPUT_LINE:0:120} $FAILED_LINE"
fi

python3 - "$HERE" "$OUT" "$RESOLVE_MODE" "$RES_RC" "$BUILD_RC" "$RUN_RC" "$WORK" "$SEMVER_OK" "$LFS_FAIL" <<'EOF'
import os, sys
here, out, resolve_mode, res_rc, build_rc, run_rc, work, semver_ok, lfs_fail = sys.argv[1:10]
sys.path.insert(0, here)
from channels_common import check, load_pins, write_result
pins = load_pins()
tag = pins["GEN_LITERTLM_TAG"]
ver = tag.lstrip("v")
checks = []

checks.append(check(
    "swiftpm.resolve-semver",
    f"SwiftPM maps exact:\"{ver}\" onto the {tag} tag",
    "PASS" if semver_ok == "1" else "FAIL",
    f"version computed: {semver_ok == '1'} (mode={resolve_mode})",
    issue="",
    evidence=f"{work}/resolve.log"))

if lfs_fail == "1":
    checks.append(check(
        "swiftpm.checkout-lfs",
        "working-copy checkout (git-lfs smudge through SwiftPM's local mirror)",
        "FAIL",
        "fatal: prebuilt/android_arm64/libGemmaModelConstraintProvider.so smudge failed — "
        "SwiftPM checks out from its local bare mirror (no LFS endpoint); the object "
        "EXISTS on GitHub LFS (batch API verified). Any consumer with git-lfs installed "
        "is blocked; measured workaround GIT_LFS_SKIP_SMUDGE=1",
        issue="LiteRT-LM#2407",
        evidence=f"{work}/resolve.log + .build/checkouts .git/lfs/logs"))
else:
    checks.append(check(
        "swiftpm.checkout-lfs", "working-copy checkout succeeds without LFS workarounds",
        "PASS" if res_rc == "0" else "FAIL",
        "clean checkout", issue="", evidence=f"{work}/resolve.log"))

def tail(name, n=4):
    try:
        return " | ".join(l.strip() for l in open(os.path.join(work, name)).readlines()[-n:])
    except Exception:
        return "(no log)"

checks.append(check(
    "swiftpm.build",
    "swift build -c release of a minimal Engine client (pulls pinned xcframeworks)",
    "PASS" if build_rc == "0" else "FAIL",
    ("built" if build_rc == "0" else tail("build.log"))[:200],
    issue="",
    evidence=f"{work}/build.log"))

if run_rc == "2" and build_rc != "0":
    checks.append(check("swiftpm.generate", "one generate on the LLM canary (CPU)",
                        "SKIP", "blocked: build failed", issue=""))
else:
    out_line = ""
    try:
        for l in open(os.path.join(work, "run.log")):
            if l.startswith(("OUTPUT:", "INIT_OK", "FAILED:")):
                out_line += l.strip()[:160] + " "
    except Exception:
        pass
    checks.append(check(
        "swiftpm.generate",
        "one generate on the LLM canary (CPU): exit 0 + non-empty OUTPUT",
        "PASS" if run_rc == "0" else "FAIL",
        (out_line or tail("run.log"))[:220],
        issue="",
        evidence=f"{work}/run.log"))

write_result("swiftpm", checks, out or None, extra={"resolve_mode": resolve_mode})
sys.exit(1 if any(c["status"] == "FAIL" for c in checks) else 0)
EOF
