# 0.18.0 day-0 pack — the TTS and ASR half

Companion to rows 3 and 11 of [day0-0.18.0.md](day0-0.18.0.md): (a) what the single-file load check reads, (b) how the asr-rtf column is taken on 0.18.0, (c) the own TTS assets and what a Kokoro-type single file would need from each, (d) the signals that the bundle convention changed. Written 2026-09-26 (round 2) against LiteRT-LM `main` at e2952685d, the `lt0171run` venv (litert-lm 0.17.1), edge-llm-bench HEAD 7d74707 and the Hugging Face API; no model, wheel or release asset was downloaded, nothing was built, and no device was used. Each section says what was checked (seen with `ls`, arguments read from `--help`, a usage line or the source, API reads run against `main`) and marks what could not be as `not confirmed:` with the reason. This is procedure only; no number here is a verdict.

## a. Single-file load

The checks themselves are rows 3 and 11 and are not repeated here. Row 3 asks whether any 0.18.0 artifact carries the TTS or ASR engine; row 11 asks whether the 0.18.0 builder can write a TTS file. What they read, on `main` at e2952685d:

- The loader keys a TFLiteModel section by its `model_type` metadata string and accepts the `TtsMetadata` / `AsrMetadata` enum names there (`tf_lite_acoustic`, `tf_lite_vocoder`, …); it keys a GenericBinaryData section by its metadata item `name` ([litert_lm_loader.cc:83-91](https://github.com/google-ai-edge/LiteRT-LM/blob/e2952685dd50c6ed24f067849a218d6249641c7b/runtime/util/litert_lm_loader.cc#L83-L91), [:190-199](https://github.com/google-ai-edge/LiteRT-LM/blob/e2952685dd50c6ed24f067849a218d6249641c7b/runtime/util/litert_lm_loader.cc#L190-L199)).
- Kokoro reads two TFLite sections, `tf_lite_acoustic` and `tf_lite_vocoder` ([kokoro_factory.cc:93, :101](https://github.com/google-ai-edge/LiteRT-LM/blob/e2952685dd50c6ed24f067849a218d6249641c7b/omni/tts/kokoro/kokoro_factory.cc#L88-L105)); GenericBinaryData `espeak-ng` (optional: without it the phonemizer falls back to data next to the model, :109-112), `<lang>-textnorm` and `<lang>-lexicon` (:125-140), and every remaining name as a voice (:222), each voice a 510×256 float vector, default `af_heart` ([common.h:208-225](https://github.com/google-ai-edge/LiteRT-LM/blob/e2952685dd50c6ed24f067849a218d6249641c7b/omni/tts/kokoro/common.h#L208-L225)).
- Qwen3-TTS loads from a folder only (row 11, Expected).
- The builder in the 0.17.1 wheel writes GenericBinaryData (`LitertLmFileBuilder.add_generic_binary_data(path, additional_metadata)`, or `section_type = "GenericBinaryData"` in a TOML file) but cannot type a TFLite section `tf_lite_acoustic` or `tf_lite_vocoder`: `TfLiteModelType` has 15 values, none of them TTS, and `add_tflite_model` raises "Model type metadata cannot be overridden." when `additional_metadata` carries a `model_type` (`litertlm_builder.py:722-723` in the installed wheel). It has no TtsMetadata adder.

A load test only makes sense once row 3 reads "shipped" or row 11 reads "writer". Then the file is inspected with `litert-lm-peek --litertlm_file <file>` (checked on 0.17.1: `--litertlm_file`, `--dump_files_dir`). Not confirmed: what 0.17.1's peek prints for a GenericBinaryData or TtsMetadata section; no such file exists on this machine.

## b. The asr-rtf 0.18.0 column

The 2026-09-19 instrument (edge-llm-bench [`docs/asr-rtf-v1.md`](https://github.com/john-rocky/edge-llm-bench/blob/main/docs/asr-rtf-v1.md) lines 63-68, `results/raw/2026-09-19-asr-rtf-v1-m4max-mac/PROVENANCE.md` lines 24-56) rewritten for the tag commit. Checked: the local clone's remotes (`origin` = google-ai-edge/litert-lm, `v0.17.0` and `v0.17.1` already fetched), `bazelisk`, `git lfs pull --include`, `./bench matrix --help`, and the usage lines and environment variables of the four scripts. Not confirmed: the build itself at the tag.

Mac:

1. Tag commit: `git -C ~/code/litert-lm fetch origin tag v0.18.0 --no-tags`, then `SHA=$(git -C ~/code/litert-lm rev-parse --short=8 'v0.18.0^{commit}')`.
2. Worktree, as `~/code/litert-lm-1dadd00c-wt` was made: `GIT_LFS_SKIP_SMUDGE=1 git -C ~/code/litert-lm worktree add --detach ~/code/litert-lm-$SHA-wt v0.18.0`.
3. The Metal accelerator from LFS: `cd ~/code/litert-lm-$SHA-wt && git lfs pull origin --include="prebuilt/macos_arm64/libLiteRtMetalAccelerator.dylib"`.
4. Confirm the target at the tag with row 3's `omni/` `cc_binary` loop (`omni/asr/BUILD 1` on e2952685d, lines 624-625), then `bazelisk build //omni/asr:asr_runner` (bazel from `.bazelversion`, 7.6.1 at 1dadd00c; `.bazelrc` defaults: `-c opt`, macOS config; the 09-19 build ran 06:16:24–06:19:38).
5. Run dir named for the tag commit: `D=~/code/edge-llm-bench/.build/asr-runner-$SHA && mkdir -p $D && cp bazel-bin/omni/asr/asr_runner omni/asr/model_metadata.json prebuilt/macos_arm64/libLiteRtMetalAccelerator.dylib $D/ && echo "v0.18.0@$SHA" > $D/ENGINE_VERSION && (cd $D && shasum -a 256 * > SHA256SUMS)`. Not confirmed: where `libLiteRtTopKMetalSampler.dylib` comes from for 0.18.0. The 09-19 dir took it from the v0.17.0 release, and only the Qwen3-ASR decoder's GPU sampler uses it (PROVENANCE.md, the run-dir table).
6. The cells: `cd ~/code/edge-llm-bench && ASR_RUNNER_DIR=.build/asr-runner-$SHA ./bench matrix matrices/asr-rtf-v1.cells --platform mac --campaign $(date +%Y-%m-%d)-asr-rtf-v1-v0180-m4max-mac` (usage `bench matrix [--platform {mac,iphone,android}] [--campaign CAMPAIGN] cells`; eight `mac` ASR rows plus the MLX anchor). `ASR_ENGINE_VERSION` defaults to the run dir's `ENGINE_VERSION` and `ASR_MODEL_DIR` to `.build/asr-models`; without `ASR_RUNNER_DIR` the driver falls back to `.build/asr-runner-1dadd00c` (`scripts/asr_rtf_mac.py:367`). Each launch is the `asr_runner` line of PROVENANCE.md:52 with the new run dir.

Galaxy S26, same worktree (`docs/asr-rtf-v1.md:113-121`): `bazelisk build --config=android_arm64 --enable_platform_specific_config //omni/asr:asr_runner` (NDK r28 through `ANDROID_NDK_HOME`); stage the runner, the `prebuilt/android_arm64/` GPU `.so` files (LFS), `model_metadata.json`, `ENGINE_VERSION` and `SHA256SUMS` in `.build/asr-runner-$SHA-android/`, using the `.so` list of `.build/asr-runner-1dadd00c-android/`; then `ASR_ANDROID_RUNNER_DIR=.build/asr-runner-$SHA-android python3 scripts/asr_rtf_android.py matrices/asr-rtf-v1.cells --campaign <name>` (the script is not executable, mode 644; the phone from `--serial` or `BENCH_ANDROID_SERIAL`, never guessed; records in `results/raw/<campaign>-android/`).

iPhone, same worktree (`docs/asr-rtf-v1.md:139-160`): copy edge-llm-bench `tools/asr-bench-ios/` into the worktree as `bench_ios/`, `git lfs pull origin --include=prebuilt/ios_arm64/libLiteRtMetalAccelerator.dylib`, `scripts/build_asr_bench_ios.sh ~/code/litert-lm-$SHA-wt` (30-60 min from a cold output base), then `ASR_IOS_METADATA=~/code/litert-lm-$SHA-wt/omni/asr/model_metadata.json scripts/asr_rtf_iphone.py matrices/asr-rtf-v1.cells --campaign <name>` (the phone from `--device` or `BENCH_UDID`; records in `results/raw/<campaign>-ios/`; the metadata default is the 66058c82 copy). Not confirmed: whether the shim, written against `main` at 66058c82 on 09-25, still compiles against the tag's `omni/asr` API.

## c. Own TTS assets and the Kokoro-type layout

File names are the Hub API siblings (`/api/models/<id>?blobs=true`, 2026-09-26). Roles come from each repo's card at that revision, with its line numbers; "Voices" means voice data shipped in the repo.

Six own TTS repos:

| Repo @ revision | Graphs (`.tflite`) and role | Voices | Other files |
|---|---|---|---|
| `litert-community/kitten-tts-nano-0.8` @ d4662d89 | `kitten_predictor` (`input_ids`, `style`, `speed` → `d`, `t_en`, `durations`), `kitten_prosody` (`en`, `style` → `f0`, `n`, `har`), `kitten_vocoder` (`asr`, `f0`, `n`, `har`, `style` → wav at 24 kHz), each also as `_fp16`; `kitten_vocoder_static80` (a static 80-frame vocoder chunk, a GPU experiment) (card L51-53, L209) | `voices.npz`, 8 style vectors; the style input is [1,256] (L51, L210) | `say.py`, `bench.py`, `bench_inputs.npz`, `make_bench_inputs.py`, `samples/`. Phoneme ids: espeak-ng IPA, the 178-symbol Kokoro / StyleTTS2 table (L238) |
| `litert-community/Matcha-TTS` @ 143eb423 | `matcha_textenc_fp16` (text encoder: `emb`, `mask` → `mu`, `logw`), `matcha_decoder_fp16` (CFM decoder, one call per ODE step), `matcha_vocoder_fp16` (HiFi-GAN: mel → wav, 22.05 kHz), `dp_g2p_matcha_fp16` (G2P: char ids → IPA logits) (card L48-51) | none: one LJSpeech voice (L32) | `emb.bin` (phoneme embedding, 178×192, host), `g2p_dict.txt.gz`, `config.json`, `g2p_meta.json` (L52-54), `samples/` |
| `mlboydaisuke/Matcha-TTS-LiteRT` @ 72c756ef | the same four graphs at the same byte sizes (card L32-35) | none | the same host files, no `samples/` |
| `litert-community/Qwen3-TTS-12Hz-0.6B-Base` @ 528cca7d | `talker_int4` / `talker_fp32` (talker LM), `mtp_fp32` / `mtp_folded_int8` (the 15 residual codebooks), `codec_decoder_fp32`, or `codec_partA` + `codec_partB` (codec decoder → 24 kHz PCM) (card L52-57) | `voices/demo_speaker.npy` (x-vector, L61); cloning from about 3 s of audio (L42) | `tables/` (host embedding tables, `.npy` / `.npz`), `tokenizer.json`, `vocab.json`, `merges.txt` (L58-60) |
| `litert-community/sopro-v2-turbo` @ 31783de7 | per precision (`fp32/`, `wfp16/`, `int8/`): speaker encoder, semantic encoder, style prefix, AR prefill / step / merged, acoustic condition and velocity (the flow solver loops on the host), vocoder offline and stream start / step / flush → iSTFT features, iSTFT on the host (card L50-66, graph contract L112-126) | none: reference-conditioned; the speaker encoder takes a 10 s reference (L118, L147) | `host_assets/` (tables, DSP constants, `tokenizer.model`), `android/`, `conversion/`, `contract*.json`, `assets/` |
| `mlboydaisuke/Pocket-TTS-LiteRT` @ 66c9d2fb | `pt_flowlm_step` (AR step), `pt_flow_head` (→ latent), `pt_flowlm_fused` (step and head in one), `pt_mimi_dec_tx` (Mimi decoder transformer), `pt_mimi_deconly` (SEANet decoder → 24 kHz audio), each also as `_fp16` (card L43-47) | `voices/pt_voice_{alba,charles,eve,javert,marius,mary}.bin`, preset voices; cloning needs the gated Mimi encoder (L202-205) | `pt_embed_f16.bin`, `pt_input_linear_f32.bin`, `pt_bos_input_f32.bin`, `pt_neutral_latent_f32.bin`, `pt_tokenizer.tsv`, `samples/`, `assets/` |

Three more, found on 2026-09-26 by a Hub search of both accounts for "kokoro" and "vibe" (own by account, or by the card's link to the conversion code):

| Repo @ revision | Graphs (`.tflite`) and role | Voices | Other files |
|---|---|---|---|
| `mlboydaisuke/Kokoro-82M-LiteRT` @ 7a30f3e9 | `kokoro_predictor` (`ids`, `ref_s`, `attn` → `duration`, `d`, `t_en`), `kokoro_prosody` (`d`, `t_en`, `aln`, `ref_s`, `frame_mask` → `asr`, `F0`, `N`), `kokoro_vocoder` (`asr`, `F0`, `N`, `har`, `ref_s`, `frame_mask` → `spec`, `phase`: magnitude and phase spectrogram) (card L38-52) | none in the repo: the voice is the `ref_s` input, taken from the base repo's `voices/*.pt` (L56) | `istft_Wr_f32.bin`, `istft_Wi_f32.bin` (host iSTFT bases, L53) |
| `litert-community/Kokoro-82M` @ 5c76448f | the same three graphs at the same byte sizes, plus `kokoro_82m_fixedlen_fp32` (a single-graph fixed-length demo build) (card L40-56; conversion code: john-rocky/LiteRT-Models, L95) | none (L59) | the same iSTFT bases |
| `mlboydaisuke/VibeVoice-Realtime-0.5B-LiteRT` @ 05c7f292 | `vv_base_lm_kv_fp32` (4-layer text LM step), `vv_tts_lm_kv_fp32` (20-layer TTS LM step), `vv_diffhead_fp16` (DDPM diffusion head), `vv_decoder_fp32` (σ-VAE decoder) (card L36-40) | `voice_en-Emma_woman.bin`, a precomputed prompt KV cache (L66-67) | `embed_tokens.f16`, `glue.f32` |

G2P only, no TTS graph: `mlboydaisuke/Kokoro-G2P-en-US-LiteRT` and `litert-community/Kokoro-G2P-en-US` (`dp_g2p_litert.tflite`).

Local:

- `~/code/litert-kokoro/` (not a git repo): `export_kokoro_litert.py` exports `predictor`, `prosody` and `vocoder`; its docstring ends the vocoder line with `-> audio[LB*600]`, while the Hub card of the same-size file says `-> spec, phase`. Which one the local file emits is not confirmed (no signature was read this round). `out_litert/kokoro_{predictor,prosody,vocoder}.tflite` have the Hub Kokoro byte sizes (90,741,756 / 37,393,104 / 236,130,056); `out_litert_lb256`, `_lb256_fp16`, `_lb256_int8` and `_mixed` hold other buckets and precisions. Several of these files are links into the external archive disk (they resolved on 09-26). `android_assets/` holds `ref_s_f32.bin` (1,024 B, one 256-float style vector), `ref_input_ids_i64.bin`, reference `desk_spec.npy` / `desk_phase.npy` and the iSTFT bases.
- `~/code/LiteRT-Models/kokoro/`: an Android app on the Kokoro-82M ONNX graph through ONNX Runtime (its README, L11, L46, L60); LiteRT runs only the neural G2P there. Its voices are `voices/*.bin` from `onnx-community/Kokoro-82M-v1.0-ONNX`, 510 KB each (LiteRT-Models README L995). No LiteRT TTS graph.
- `~/code/LiteRT-Models/matcha/`: an Android app over the four `litert-community/Matcha-TTS` graphs (its README, L29-32).
- `~/code/coreai/_pockettts_demo/`: the Core AI iPhone demo of Pocket-TTS (`CoreAIKit.PocketTTS`, README L7); assets are not kept locally. Not LiteRT.
- litertlm-convert `out/qwen3tts-day0/folder/` (row 3): the seven `.tflite` files under the `Qwen3TtsModelConfig` default names, `tokenizer.json` and `voices/demo_speaker.bin`; five `.tflite` are links into the external archive disk (they resolved on 09-26).

What a Kokoro-type single file needs, on `main` at e2952685d:

1. Two TFLite sections typed `tf_lite_acoustic` and `tf_lite_vocoder` (section a).
2. An acoustic graph with inputs `phoneme_ids`, `speaker_style`, `phoneme_length` and outputs `acoustic_features`, `pitch_contour`, `energy_contour`, `speech_frame_length`, resolved by name ([kokoro_acoustic_stage.cc:97-117](https://github.com/google-ai-edge/LiteRT-LM/blob/e2952685dd50c6ed24f067849a218d6249641c7b/omni/tts/kokoro/kokoro_acoustic_stage.cc#L97-L117)).
3. A vocoder graph with inputs `acoustic_features`, `pitch_contour`, `energy_contour`, `speaker_style`, `speech_frame_length` and outputs `magnitude_spectrogram`, `phase_spectrogram` ([kokoro_vocoder_stage.cc:76-96](https://github.com/google-ai-edge/LiteRT-LM/blob/e2952685dd50c6ed24f067849a218d6249641c7b/omni/tts/kokoro/kokoro_vocoder_stage.cc#L76-L96)).
4. One GenericBinaryData section per voice, 510×256 floats, `name` = the voice name.
5. `espeak-ng` data (optional) and, for CJK, `<lang>-textnorm` / `<lang>-lexicon`.
6. Optionally a TtsMetadata section with `tts_model_type` Kokoro; without it an acoustic section makes the file Kokoro. The engine knows two model types, Kokoro and Qwen3-TTS ([tts_engine.h:41-47](https://github.com/google-ai-edge/LiteRT-LM/blob/e2952685dd50c6ed24f067849a218d6249641c7b/omni/tts/tts_engine.h#L41-L47)).

With the 0.17.1 builder, items 4 and 5 can be written and items 1 and 6 cannot, so no own asset becomes a Kokoro-type file today (row 11). What each asset lacks beyond the writer:

| Asset | Graph contract (items 2 and 3) | Voices (item 4) |
|---|---|---|
| Own Kokoro (`mlboydaisuke/Kokoro-82M-LiteRT`, `litert-community/Kokoro-82M`, `litert-kokoro/out_litert`) | three graphs, not one acoustic graph: predictor and prosody with a host alignment (`aln`) between them, where the engine expects one graph from phoneme ids to frame-level features plus `speech_frame_length`; the vocoder's output kind matches (magnitude and phase) but its names are `spec` / `phase`, and it also takes `har` and `frame_mask`. A re-export to the two-graph contract, not a re-pack | none shipped; the ONNX app's `voices/*.bin` are 510 KB each (510×256×4 B = 522,240 B), whether the format is the same: not confirmed |
| `kitten-tts-nano-0.8` | the same three-way split; the vocoder emits a waveform, not spectrograms; the engine has no Kitten type, so only the Kokoro contract applies | [1,256] style vectors in one `voices.npz`, not 510×256 per voice |
| `Qwen3-TTS-12Hz-0.6B-Base` and the day-0 folder | no single-file layout: the engine loads Qwen3-TTS from a folder ([qwen3_tts_factory.cc:43-95](https://github.com/google-ai-edge/LiteRT-LM/blob/e2952685dd50c6ed24f067849a218d6249641c7b/omni/tts/qwen3_tts/qwen3_tts_factory.cc#L43-L95)). For that folder the Hub repo lacks `text_embedding.tflite`, `text_projection.tflite`, `codec_embedding.tflite` and `mtp_embedding.tflite` (it ships `tables/*.npy` / `.npz`); the day-0 folder has them ([qwen3_tts_model_config.h:27-43](https://github.com/google-ai-edge/LiteRT-LM/blob/e2952685dd50c6ed24f067849a218d6249641c7b/omni/tts/qwen3_tts/qwen3_tts_model_config.h#L27-L43)) | the config wants `voices/demo_speaker.bin`; the Hub repo ships `.npy`, the day-0 folder `.bin` |
| Matcha (both repos), sopro, Pocket-TTS, VibeVoice | other architectures (flow matching, AR LM with a flow or diffusion head); the engine has no type for them, so no layout exists | not applicable |

Draft order for the own Kokoro graphs, blocked at step 3 until a writer ships (draft only; each upload is its own GO): (1) re-export to the two-graph contract of items 2 and 3, with those tensor names; (2) write each voice as a 510×256 float32 `.bin`; (3) build with the tag's builder, typing the two TFLite sections acoustic and vocoder and adding the voices (and `espeak-ng` if the file should not depend on data next to it) as GenericBinaryData with `name`; (4) inspect with `litert-lm-peek` and load through whatever surface row 3 finds.

## d. Signals that the convention changed

Each is read against the tag on the day; the value in brackets is `main` at e2952685d.

1. The builder types TTS sections: row 11's `TfLiteModelType` / adder print and the `tflite_model --model_type` choices gain acoustic or vocoder [15 names, none TTS; 0.17.1 wheel]. Source side, checked on e2952685d: `for f in litertlm_builder.py litertlm_peek.py litertlm_builder_cli.py litertlm_core.py; do echo "$f $(gh api "repos/google-ai-edge/LiteRT-LM/contents/python/litert_lm_builder/$f?ref=v0.18.0" --jq .content | base64 -d | grep -ciE 'tts|asr|acoustic|vocoder')"; done` [0 in all four].
2. Peek prints `TtsMetadata` or `AsrMetadata`: the same loop's `litertlm_peek.py` count [0].
3. `omni/` gains a `cc_binary` beyond `//omni/asr:asr_runner`, a TTS command line for example: row 3's loop [`omni/asr/BUILD` 1, the other five 0].
4. A binding carries TTS or ASR: `gh api 'repos/google-ai-edge/LiteRT-LM/git/trees/v0.18.0?recursive=1' --jq '.tree[].path' | grep -E '^(c|swift|python|kotlin)/' | grep -ciE 'tts|asr|omni|speech'` [0], and row 3's engine column on the shipped binaries [the engine pattern counts 0 on the v0.16.0 mac dylib; the 09-09 run's narrower TTS and ASR patterns counted 0 on all three v0.17.0 binaries].
5. The CLI gains a tts or asr command: row 3's `litert-lm --help` count [0 on 0.17.1].
6. A published `.litertlm` carries `tf_lite_acoustic` / `tf_lite_vocoder` sections, seen with `litert-lm-peek`. Where such a file would appear: not confirmed; none is known on 09-26.
