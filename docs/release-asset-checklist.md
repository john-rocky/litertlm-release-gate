# Release-asset checklist — what a version-pinned consumer gets at each LiteRT-LM tag

I ship [bundles to litert-community](https://huggingface.co/litert-community) and Swift bindings on top of the [LiteRT-LM](https://github.com/google-ai-edge/LiteRT-LM) release assets, so this gate re-runs on every tag. This page lists what those bindings and bundles read off a tag, one line each: the check, what a consumer sees without it, the command, and what the last four tags carried. Every row comes from something I hit on a published tag; nothing here is hypothetical.

The runtime under the assets is [LiteRT](https://github.com/google-ai-edge/litert); its own release zips are checked by the same runner (`ghrt.*` rows in the results tables).

## The checklist

| # | Check at the tag commit | What a consumer sees without it | v0.16.0 | v0.16.1 | v0.17.0 | v0.17.1 | Issue |
|---|---|---|---|---|---|---|---|
| 1 | `Package.swift` points both `binaryTarget`s at the **same tag's** xcframework zips, checksums matching, and `swift build` at `exact: "<tag>"` succeeds | A build failure listing the C symbols the pinned headers lack, whenever `swift/` moved since the pinned zips | pins v0.16.0 (build not measured) | pins v0.16.0 (no zips on the tag), builds | pinned v0.16.0 at tag time (945edf38f) → 37 missing symbols; the tag now sits on e9fd8c53 (v0.17.0 pins) and builds | pins v0.17.0 (the v0.17.1 zips are the same bytes: sha256 `83efd536…` mac, `c94fc12a…` iOS, measured); `exact: "0.17.1"` builds (Xcode 27.0 / Swift 6.4, 2026-09-17) | [#3296](https://github.com/google-ai-edge/LiteRT-LM/issues/3296) (pattern of #2920) |
| 2 | `litert_lm_c_api-<C_API_VERSION>.zip` on the release page (the v0.16.0 shape: `liblitert-lm` for android_arm64 / android_x86_64 / linux_arm64 / linux_x86_64 / macos_arm64 / windows_x86_64 — seven library files counting the Windows `.dll` and its `.lib` — plus `engine.h`, `conversation.h`) | Go, .NET/Unity and other non-Python bindings have nothing to pin | yes (2026-08-12) | – | paused for 0.17.x (#3569) | paused | [#3569](https://github.com/google-ai-edge/LiteRT-LM/issues/3569) |
| 3 | The README's top `litert-lm run` command runs verbatim at the tag | The first command a new reader runs returns HTTP 404 (`gemma-4-E4B-it.litertlm` requested from the `gemma-4-E2B` repo) | not measured | 404 | 404 | 404 (fixed on `main` since 49cf34756, 2026-09-04; the 0.17 branch was cut 2026-08-29) | [#3418](https://github.com/google-ai-edge/LiteRT-LM/issues/3418) / #3495 |
| 4 | `litert_lm_main.macos_arm64` on the release page | The CLI path without Python has no download for this version | yes | yes | yes (added 2026-09-09 17:19Z, after the first publication) | – | – |
| 5 | `CLiteRTLM.spdx.json` and `THIRD_PARTY_NOTICES.txt` beside the binaries, and notices inside the xcframework zips | App Store and corporate compliance cannot attach notices to the binary they ship | yes (2026-08-21) | – | – | – | [#3194](https://github.com/google-ai-edge/LiteRT-LM/issues/3194) |

Cells are what the release page and the tag commit showed at check time (v0.16.x: 2026-08-31 and 09-06 passes; v0.17.0: 2026-09-08 21:50Z and 09-13; v0.17.1: 2026-09-17 02:30Z). The v0.17.0 release first appeared 2026-09-08 20:56Z on 945edf38f; when the tag moved to e9fd8c53 the release object was re-created (createdAt 09-09 16:51Z, publishedAt 17:06Z), which is the date the page shows today. Full tables with every PASS row: [results/](../results/).

## How I check each row

Rows 2, 4 and 5 are the asset list; row 1 is the manifest at the tag commit plus one build; row 3 is one command in a fresh environment.

```bash
gh release view v0.17.1 --repo google-ai-edge/LiteRT-LM --json assets --jq '.assets[] | "\(.name) \(.size) \(.updatedAt)"'
gh api 'repos/google-ai-edge/LiteRT-LM/contents/Package.swift?ref=v0.17.1' --jq .content | base64 -d | grep -n -A2 'url:'
gh api 'repos/google-ai-edge/LiteRT-LM/contents/README.md?ref=v0.17.1' --jq .content | base64 -d | grep -n -B2 -A2 'gemma-4-E4B-it.litertlm'
unzip -l CLiteRTLM_mac.xcframework.zip | grep -ciE 'NOTICE|spdx|THIRD_PARTY'
```

The gate runs the same five rows as `ghlm.*`, `swiftpm.*` and `quickstart.*` checks (`./run_channels.sh --only gh_assets,swiftpm,quickstart` after moving `GEN_LITERTLM_TAG` in `pins.env`).

## Notes on the rows

- **Row 1 only shows up for version pins.** `main` moves its pins to the new zips about an hour after each tag (8ef538581 for v0.17.0, 9465fc262 for v0.17.1), so a `branch: "main"` consumer never sees it. A consumer on `exact:` resolves the tag commit, whose manifest predates that bump. It only hurts when `swift/` gained C calls since the pinned zips: v0.17.0 did (37 symbols), v0.17.1 did not (one cherry-pick, no Swift change). `main` today calls `model_info.h` and `error_reporter.h` symbols the v0.17.1 zips do not ship (their header set is `engine.h`, `conversation.h`, `capabilities.h`, `embedding_engine.h`, `experimental.h`), which is what row 1 measures on the next tag.
- **Row 2 is paused by their decision for 0.17.x** (a rename in progress, per whhone on #3569, with the C API release to resume). `version.bzl` on `main` carries `C_API_VERSION = "0.2.0"`, so the next zip would be `litert_lm_c_api-0.2.0.zip`; a `paused` cell is not a failure of the tag.
- **Row 3 follows the branch cut.** The fix has been on `main` for two weeks; the 0.17.x tags are cut from 2026-08-29. A tag cut from `main` after 09-04 passes on its own.
- **Not a row: the OpenCL accelerator's `DT_NEEDED` (#3575).** Measured 2026-09-17: neither the `litertlm-android` AAR (0.16.0 and 0.17.0 ship only `liblitertlm_jni.so`, which links `libandroid.so`) nor the v0.16.0 C-API zip (seven `liblitert-lm` library files for six platforms; the android_arm64 one links `libandroid.so`) contains `libLiteRtOpenClAccelerator.so`. The accelerator in #3575 ships inside a package its author builds from source (their note on #3569 links the build scripts), so no published LiteRT-LM asset carries the row. If a future C-API zip ships the accelerator, the check is `llvm-readelf -d libLiteRtOpenClAccelerator.so | grep NEEDED` listing `libandroid.so`.
- **Not a row: channel lag.** PyPI, Maven and npm published 0.17.0 on 2026-09-04 (22:00–22:15 UTC), four days before the GitHub tag; PyPI published 0.17.1 twenty-two hours before its tag. That is a timing fact the results tables record; nothing arrives broken because of it.
