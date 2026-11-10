# Notes that save time

- **litert.js is published for bundlers**: `dist/index.js` imports the bare specifier `@litertjs/wasm-utils`, so the no-bundler smoke serves it via an import map (`npm_smoke/smoke.html`).
- **Headless Chrome can linger after `--dump-dom`**; the runner polls for the page's `RESULT:` marker and kills it. `performance.now()` under `--virtual-time-budget` is virtual, so the smoke's `infer_ms` is meaningless — only the finite-output verdict counts.
- **litertlm-android 0.16.1 ships Kotlin metadata 2.3.0**: consumers on Kotlin ≤ 2.1 fail to compile against it ("can read up to 2.2.0"), so the harness app pins Kotlin 2.2.10.
- **SwiftPM checkout of LiteRT-LM dies on git-lfs** (`prebuilt/.../libGemmaModelConstraintProvider.so`): SwiftPM checks out from its local bare mirror, which has no LFS endpoint — the object itself is fine on GitHub's LFS. The runner records the FAIL, then continues under `GIT_LFS_SKIP_SMUDGE=1` so build and generate still get measured. First `swift package resolve` also mirrors the full repo history (~3.2 GB / ~14 min measured).
- **The litert-lm CLI reads HF auth only from `--huggingface-token` / `HF_TOKEN`**; gated repos (even auto-approved ones) 401 without it. Gating failures are recorded as SKIP, not channel FAILs.
- Non-interactive `litert-lm run` always gets `</dev/null` — it blocks forever on an inherited tty otherwise.
