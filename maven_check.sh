#!/bin/bash
# Channel: Maven (Google Maven) — does the litertlm-android AAR resolve, build
# into an app, and survive init + ONE text generate on a real device?
#
#   ./maven_check.sh [--out DIR] [--no-device]
#
# The device leg is where #3334 (NoSuchMethodError SendChannel.close$default at
# end of turn) and #3266 (onDone never called -> collect hangs) live; the runner
# classifies the instrumentation output into exactly those shapes. If several
# harnesses share the phone, coordinate externally — a contended device produces
# wrong-looking numbers, not errors.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=""; NODEV=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --no-device) NODEV=1; shift ;;
    *) echo "usage: $0 [--out DIR] [--no-device]"; exit 2 ;;
  esac
done
V=$(grep '^GEN_MAVEN_LITERTLM_ANDROID=' "$HERE/pins.env" | cut -d= -f2)
export JAVA_HOME="${JAVA_HOME:-/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home}"
LOGD="$HERE/cache/maven_work"; mkdir -p "$LOGD"
cd "$HERE/maven_android"

# ---- 1. dependency resolution from Google Maven
./gradlew --no-daemon -PlitertlmVersion="$V" :app:dependencies \
  --configuration debugRuntimeClasspath > "$LOGD/dep.log" 2>&1
DEP_RC=$?
RESOLVED=$(grep -m1 "com.google.ai.edge.litertlm:litertlm-android:$V" "$LOGD/dep.log" || true)
COROUTINES=$(grep -oE 'kotlinx-coroutines-core[a-z-]*:[0-9][0-9.]*[0-9]( -> [0-9][0-9.]*[0-9])?' "$LOGD/dep.log" | sort -u | tail -3 | tr '\n' ' ')
echo "[maven] resolve rc=$DEP_RC resolved='${RESOLVED:0:80}' coroutines='$COROUTINES'"

# ---- 2. build app + androidTest APKs
./gradlew --no-daemon -PlitertlmVersion="$V" :app:assembleDebug :app:assembleDebugAndroidTest \
  > "$LOGD/build.log" 2>&1
BUILD_RC=$?
echo "[maven] build rc=$BUILD_RC $(tail -1 "$LOGD/build.log")"

# ---- 3. device leg
DEV_STATE="not-run"; DEV_RC=99; DEVICE_MODEL=""

if [ $BUILD_RC -ne 0 ]; then
  DEV_STATE="skip:build-failed"
elif [ "$NODEV" = "1" ]; then
  DEV_STATE="skip:--no-device"
elif ! adb get-state >/dev/null 2>&1; then
  DEV_STATE="skip:no-adb-device"
else
  DEVICE_MODEL=$(adb shell getprop ro.product.model </dev/null 2>/dev/null | tr -d '\r\n')
  {
    CANARY=$(python3 - "$HERE" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
from channels_common import load_pins, resolve_canary
p = load_pins()
path, src = resolve_canary(p["CANARY_LLM_REPO"], p["CANARY_LLM_FILE"])
print(path)
EOF
)
    adb shell mkdir -p /data/local/tmp/relgate </dev/null
    adb push "$CANARY" /data/local/tmp/relgate/canary.litertlm </dev/null > "$LOGD/push.log" 2>&1
    adb shell chmod 755 /data/local/tmp/relgate </dev/null
    adb shell chmod 644 /data/local/tmp/relgate/canary.litertlm </dev/null
    adb logcat -c </dev/null 2>/dev/null

    ./gradlew --no-daemon -PlitertlmVersion="$V" :app:connectedDebugAndroidTest \
      > "$LOGD/connected.log" 2>&1
    DEV_RC=$?
    DEV_STATE="ran"
    adb logcat -d -s RELGATE:I AndroidRuntime:E TestRunner:E </dev/null > "$LOGD/logcat.txt" 2>&1
    cp -R app/build/outputs/androidTest-results/connected "$LOGD/androidTest-results" 2>/dev/null

    adb shell rm -rf /data/local/tmp/relgate </dev/null
    adb uninstall dev.relgate.litertlm </dev/null >/dev/null 2>&1
    adb uninstall dev.relgate.litertlm.test </dev/null >/dev/null 2>&1
    echo "[maven] device rc=$DEV_RC on $DEVICE_MODEL"
  }
fi

python3 - "$HERE" "$OUT" "$V" "$DEP_RC" "$BUILD_RC" "$DEV_STATE" "$DEV_RC" "$DEVICE_MODEL" "$LOGD" <<'EOF'
import glob, os, re, sys
(here, out, ver, dep_rc, build_rc, dev_state, dev_rc, device_model, logd) = sys.argv[1:10]
sys.path.insert(0, here)
from channels_common import check, write_result
checks = []

def logtext(name):
    try:
        return open(os.path.join(logd, name), errors="replace").read()
    except Exception:
        return ""

dep = logtext("dep.log")
resolved = f"com.google.ai.edge.litertlm:litertlm-android:{ver}" in dep
coro = sorted(set(re.findall(r"kotlinx-coroutines-core[a-z-]*:[0-9.]+(?: -> [0-9.]+)?", dep)))
checks.append(check(
    "maven.resolve", f"litertlm-android:{ver} resolves from google() Maven",
    "PASS" if (dep_rc == "0" and resolved) else "FAIL",
    f"resolved={resolved}; coroutines on the app classpath: {coro[:3]}",
    issue="", evidence=f"{logd}/dep.log"))

checks.append(check(
    "maven.build", "app + androidTest APKs assemble against the AAR",
    "PASS" if build_rc == "0" else "FAIL",
    "assembled" if build_rc == "0" else " | ".join(logtext("build.log").splitlines()[-4:])[:200],
    issue="", evidence=f"{logd}/build.log"))

if dev_state != "ran":
    checks.append(check(
        "maven.device-init-generate", "init + one generate via instrumented test",
        "SKIP", dev_state, issue="", evidence=""))
else:
    blob = logtext("connected.log") + logtext("logcat.txt")
    for x in glob.glob(os.path.join(logd, "androidTest-results", "**", "*.xml"), recursive=True):
        blob += open(x, errors="replace").read()
    nsme = re.search(r"NoSuchMethodError[^\n]*close\$default", blob)
    timeout = re.search(r"TimeoutCancellationException|Timed out waiting", blob)
    crashed = re.search(r"Test instrumentation process crashed|Process crashed", blob)
    answer = re.search(r"ANSWER: (.{0,80})", blob)
    if dev_rc == "0":
        st, meas, issue = "PASS", f"test passed on {device_model}; {answer.group(0) if answer else 'no ANSWER line captured'}", ""
    elif nsme:
        st, meas, issue = "FAIL", f"NoSuchMethodError SendChannel.close$default on {device_model} (end of first turn)", "LiteRT-LM#3334"
    elif timeout:
        st, meas, issue = "FAIL", f"collect() never completed (timeout) on {device_model}", "LiteRT-LM#3266"
    elif crashed:
        st, meas, issue = "FAIL", f"instrumentation process crashed on {device_model}: {blob[-160:]!r}", ""
    else:
        st, meas, issue = "FAIL", f"rc={dev_rc} on {device_model}; tail: {logtext('connected.log')[-160:]!r}", ""
    checks.append(check(
        "maven.device-init-generate",
        "init + ONE text generate on-device (the #3334/#3266 end-of-turn path)",
        st, meas, issue=issue,
        evidence=f"{logd}/connected.log, {logd}/logcat.txt"))

write_result("maven", checks, out or None,
             extra={"aar_version": ver, "device": device_model or None})
sys.exit(1 if any(c["status"] == "FAIL" for c in checks) else 0)
EOF
