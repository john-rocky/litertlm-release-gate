# What each channel checks

| Runner | Checks |
|---|---|
| `npm_check.sh` | `npm pack` of `@litert-lm/core` and `@litertjs/core`: tarball contents vs each package's own `files` globs, version lag vs the release tag, then a **headless-Chrome smoke that runs a real .tflite inference** from the packed litert.js artifact (wasm accelerator). |
| `maven_check.sh` | `litertlm-android` resolves from `google()` Maven, an app + instrumented test build against it, then **init + one text generate on a real device** — the end-of-turn path where the runtime's stream channel closes. |
| `gh_assets_check.py` | Release-asset content: SwiftPM `Package.swift` binary URLs resolve and **sha256 matches the declared checksum**, capabilities C API presence in the xcframework and C-API zips, NOTICE/SBOM presence, vendor dirs inside the LiteRT NPU runtime zips, no zero-byte members. |
| `swiftpm_check.sh` | `swift package resolve` of the official package at the pinned tag (semver `exact`), checkout, `swift build`, then one generate through the Swift `Engine` API on a small canary model. |
| `scoring_rewind_check.py` | Text scoring after one prefill on the wheel's C API (ctypes over `liblitert-lm.dylib`, Mac CPU): `run_prefill` → `save_checkpoint` → per candidate `run_text_scoring` + `rewind_to_checkpoint`, **each score asserted against a fresh session with a fresh prefill**, then the first candidate scored again. Rows `scoring.first` / `scoring.rewind` / `scoring.repeat`; on 0.17.x the last two FAIL with google-ai-edge/LiteRT-LM#3561 (fix proposed in #3562), so the canary is the day-0 check of that fix. |
| `quickstart_check.sh` | The README's own commands, run **verbatim** (drift-checked against the tag first): `uv tool install litert-lm`, the Quick Try block, the header gemma-4 command — plus the same flow with a small ungated model to separate pipe health from broken/gated documented commands. |

PyPI is exercised along the way: `uv tool install litert-lm` resolves from PyPI, and the swapped-model quickstart leg takes that CLI through download and generation.

Verdicts: `PASS` / `FAIL` / `SKIP` (blocked, e.g. by model gating — a SKIP is "not measured", never a pass). Every FAIL in a results table carries the upstream issue it maps to; a FAIL with no issue number is a candidate new finding.

## Running and requirements

Each runner also works standalone (`./npm_check.sh`, `python3 gh_assets_check.py`, …). Results land in `results_<date>/` as one JSON per channel; `make_table.py` merges them into a markdown PASS/FAIL table under `results/`.

On a new release: update the `GEN_*` pins in `pins.env`, run, and diff the table against the previous generation. A FAIL→PASS flip is a fix confirmed; a PASS→FAIL flip is a release regression; a FAIL with no known-issue mapping is a new finding.

Downstream wrappers: [wrappers/TABLE.md](../wrappers/TABLE.md) lists the LiteRT-LM version pinned by each wrapper and app in `wrappers/wrappers.json` (file, line and commit link) and how many stable releases are newer; regenerate it with `python3 wrappers/wrappers_table.py` (Python standard library; reads GitHub through `gh` or `GITHUB_TOKEN`). Steps and host requirements: [wrappers/README.md](../wrappers/README.md).

macOS host (Apple silicon tested) with: `python3` (stdlib only), `npm`, Google Chrome, `uv`, Xcode (SwiftPM row), JDK 17 + Android SDK + one `adb` device (Maven device leg; skipped cleanly when absent), `gh` (optional, raises GitHub API limits). Models and versions are pinned in `pins.env`; the LLM canary is the smallest official litert-community ship (`gemma-3-270m-it` q8) so the model is never the variable.
