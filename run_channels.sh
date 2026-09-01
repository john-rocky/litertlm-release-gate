#!/bin/bash
# run_channels.sh — the one command for the release-artifact gate (all channels).
#
#   ./run_channels.sh                 # all rows + table
#   ./run_channels.sh --no-device     # skip the phone leg
#   ./run_channels.sh --only npm,swiftpm
#
# Rows run sequentially (each is network-heavy; parallel runs contend on the
# shared line and on the shared phone). A row failing does NOT stop the rest —
# the table is the product, and a FAIL is a result, not an abort.
#
# Before running on a NEW release: update pins.env (GEN_*), then this. Runner
# doctrine: a runner that has not been run today is assumed broken (README).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODEV=""; ONLY="npm,maven,gh_assets,swiftpm,quickstart"
while [ $# -gt 0 ]; do
  case "$1" in
    --no-device) NODEV="--no-device"; shift ;;
    --only) ONLY="$2"; shift 2 ;;
    *) echo "usage: $0 [--no-device] [--only npm,maven,gh_assets,swiftpm,quickstart]"; exit 2 ;;
  esac
done
OUTDIR="$HERE/results_$(date +%Y%m%d)"
mkdir -p "$OUTDIR"
export CHANNELS_OUT="$OUTDIR"
RC=0

has() { case ",$ONLY," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

has gh_assets  && { echo "===== gh_assets";  python3 "$HERE/gh_assets_check.py" --out "$OUTDIR" || RC=1; }
has npm        && { echo "===== npm";        "$HERE/npm_check.sh" --out "$OUTDIR" || RC=1; }
has swiftpm    && { echo "===== swiftpm";    "$HERE/swiftpm_check.sh" --out "$OUTDIR" || RC=1; }
has quickstart && { echo "===== quickstart"; "$HERE/quickstart_check.sh" --out "$OUTDIR" || RC=1; }
has maven      && { echo "===== maven";      "$HERE/maven_check.sh" --out "$OUTDIR" $NODEV || RC=1; }
echo "===== table"
python3 "$HERE/make_table.py" --results "$OUTDIR" || RC=1
echo
echo "FAILs with no issue number are DRAFT-ONLY findings — posting needs user GO."
exit $RC
