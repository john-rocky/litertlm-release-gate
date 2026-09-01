# litertlm-release-gate

Per-channel install-and-run checks over a [LiteRT-LM](https://github.com/google-ai-edge/LiteRT-LM) release: for npm, Maven (Android), the GitHub release assets, SwiftPM (macOS), and the README quickstart, each runner answers one question — **does what a user gets today actually install and generate?** Content checks, not existence checks: tarballs are unpacked, zips are diffed against their declared checksums, models really decode.

I ship [conversions on top of LiteRT-LM](https://huggingface.co/litert-community); this gate exists because litert-lm 0.15.0 silently invalidated bundles I had already shipped, and I found out from a user rather than from a check. It now runs on every release. First full pass (v0.16.1 generation): [results/v0.16.1-generation.md](results/v0.16.1-generation.md) — 35 checks, every FAIL mapped to a filed issue.

## Run it

```bash
./run_channels.sh                 # all channels + summary table
./run_channels.sh --no-device     # skip the Android phone leg
./run_channels.sh --only npm,swiftpm
```

Each runner also works standalone (`./npm_check.sh`, `python3 gh_assets_check.py`, …). Results land in `results_<date>/` as one JSON per channel; `make_table.py` merges them into a markdown PASS/FAIL table under `results/`.

On a new release: update the `GEN_*` pins in `pins.env`, run, and diff the table against the previous generation. A FAIL→PASS flip is a fix confirmed; a PASS→FAIL flip is a release regression; a FAIL with no known-issue mapping is a new finding.

## What each channel checks

| Runner | Checks |
|---|---|
| `npm_check.sh` | `npm pack` of `@litert-lm/core` and `@litertjs/core`: tarball contents vs each package's own `files` globs, version lag vs the release tag, then a **headless-Chrome smoke that runs a real .tflite inference** from the packed litert.js artifact (wasm accelerator). |
| `maven_check.sh` | `litertlm-android` resolves from `google()` Maven, an app + instrumented test build against it, then **init + one text generate on a real device** — the end-of-turn path where the runtime's stream channel closes. |
| `gh_assets_check.py` | Release-asset content: SwiftPM `Package.swift` binary URLs resolve and **sha256 matches the declared checksum**, capabilities C API presence in the xcframework and C-API zips, NOTICE/SBOM presence, vendor dirs inside the LiteRT NPU runtime zips, no zero-byte members. |
| `swiftpm_check.sh` | `swift package resolve` of the official package at the pinned tag (semver `exact`), checkout, `swift build`, then one generate through the Swift `Engine` API on a small canary model. |
| `quickstart_check.sh` | The README's own commands, run **verbatim** (drift-checked against the tag first): `uv tool install litert-lm`, the Quick Try block, the header gemma-4 command — plus the same flow with a small ungated model to separate pipe health from broken/gated documented commands. |

PyPI is exercised along the way: `uv tool install litert-lm` resolves from PyPI, and the swapped-model quickstart leg takes that CLI through download and generation.

Verdicts: `PASS` / `FAIL` / `SKIP` (blocked, e.g. by model gating — a SKIP is "not measured", never a pass). Every FAIL in a results table carries the upstream issue it maps to; a FAIL with no issue number is a candidate new finding.

## Requirements

macOS host (Apple silicon tested) with: `python3` (stdlib only), `npm`, Google Chrome, `uv`, Xcode (SwiftPM row), JDK 17 + Android SDK + one `adb` device (Maven device leg; skipped cleanly when absent), `gh` (optional, raises GitHub API limits). Models and versions are pinned in `pins.env`; the LLM canary is the smallest official litert-community ship (`gemma-3-270m-it` q8) so the model is never the variable.

## Notes that save time

- **litert.js is published for bundlers**: `dist/index.js` imports the bare specifier `@litertjs/wasm-utils`, so the no-bundler smoke serves it via an import map (`npm_smoke/smoke.html`).
- **Headless Chrome can linger after `--dump-dom`**; the runner polls for the page's `RESULT:` marker and kills it. `performance.now()` under `--virtual-time-budget` is virtual, so the smoke's `infer_ms` is meaningless — only the finite-output verdict counts.
- **litertlm-android 0.16.1 ships Kotlin metadata 2.3.0**: consumers on Kotlin ≤ 2.1 fail to compile against it ("can read up to 2.2.0"), so the harness app pins Kotlin 2.2.10.
- **SwiftPM checkout of LiteRT-LM dies on git-lfs** (`prebuilt/.../libGemmaModelConstraintProvider.so`): SwiftPM checks out from its local bare mirror, which has no LFS endpoint — the object itself is fine on GitHub's LFS. The runner records the FAIL, then continues under `GIT_LFS_SKIP_SMUDGE=1` so build and generate still get measured. First `swift package resolve` also mirrors the full repo history (~3.2 GB / ~14 min measured).
- **The litert-lm CLI reads HF auth only from `--huggingface-token` / `HF_TOKEN`**; gated repos (even auto-approved ones) 401 without it. Gating failures are recorded as SKIP, not channel FAILs.
- Non-interactive `litert-lm run` always gets `</dev/null` — it blocks forever on an inherited tty otherwise.

## License

Apache-2.0. Issue numbers referenced in runners and results point at [google-ai-edge/LiteRT-LM](https://github.com/google-ai-edge/LiteRT-LM/issues) and [google-ai-edge/LiteRT](https://github.com/google-ai-edge/LiteRT/issues).
