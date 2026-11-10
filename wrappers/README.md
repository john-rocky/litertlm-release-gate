# Downstream wrapper versions

`TABLE.md` lists the LiteRT-LM version that each wrapper and app in `wrappers.json` pins, where the pin is (file, line and commit link), and how many stable LiteRT-LM releases are newer. `table.json` holds the same rows for diffing one release against the next.

## Regenerate

```sh
python3 wrappers/wrappers_table.py
```

Run it from the repository root. It needs Python 3 (standard library only) and GitHub access through `gh` or `GITHUB_TOKEN`. One run makes about 140 GitHub API calls plus a few registry calls (npm, pub.dev, crates.io, NuGet, Google Maven) and takes under a minute. Two consecutive runs give identical files; runs further apart differ in the Last push and Downloads columns.

## When LiteRT-LM releases

1. Read the latest version on each channel: the GitHub release (and whether it ships `CLiteRTLM.xcframework.zip`), Google Maven `litertlm-android`, npm `@litert-lm/core`. The channels do not always move together, and some versions exist on one channel only.
2. Regenerate the table and diff `table.json` against the previous commit: pins that moved, open bump PRs or issues that appeared or closed, and rows with a non-empty `errors` field.
3. Open every link in `TABLE.md` before committing. GitHub returns 404 for `/tree/<sha>/<submodule path>`, so a submodule pin links the parent directory and the submodule commit separately.

## Adding a row

Add an entry to `wrappers.json`, starting from an existing entry of the same ecosystem. The table lists libraries and packages that pin LiteRT-LM directly, plus a few apps (`"kind": "app"` in `table.json`). Projects that use LiteRT without LiteRT-LM, example and sample projects, forks that only rebuild a binary, and projects that reach LiteRT-LM through another listed package are left out. A pin deep in a monorepo (a `Package.swift` under `LocalPackages/`, a `hook/build.dart` under `packages/`, a CDN URL in an example's `web/index.html`) is easy to miss: find it in the repository tree and check the new row's pin before committing.

## Host requirements that change with litertlm-android

From the published POMs and AAR manifests, and app builds against 0.19.1 on 2026-11-10:

| From | Change | Effect on an app |
|---|---|---|
| 0.15.0 | the AAR declares minSdk 24 (0.10.0 to 0.14.0: 23) | an app with minSdk 23 fails the manifest merge |
| 0.17.0 | the POM brings kotlin-stdlib 2.4.0 (through kotlin-reflect 2.4.0) | an app module that compiles Kotlin needs Kotlin 2.3 or newer (2.2.21 failed, 2.3.0 compiled); Java-only app modules are not affected |

The iOS `CLiteRTLM.xcframework` has a minimum of iOS 15.0 in both v0.13.0 and v0.19.1 (the two versions checked). From v0.19.0 its C API is 1.0.0, so a copy of the Swift sources must come from the same release as the xcframework.
