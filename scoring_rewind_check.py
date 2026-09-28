#!/usr/bin/env python3
"""scoring_rewind_check.py — text scoring after one prefill, checked against a fresh session.

The shape a closed-set decision uses from the C API: run_prefill once, save_checkpoint, then for
each candidate run_text_scoring and rewind_to_checkpoint. Every candidate's score is compared with
the score the same runtime gives on a fresh session with a fresh prefill for that candidate alone;
the first candidate is scored once more at the end. Three rows:

  scoring.first   the first candidate after the checkpoint equals its fresh-session score
  scoring.rewind  every candidate equals its fresh-session score (the rewind restored the session)
  scoring.repeat  the first candidate scored again after the rewinds equals its first score

On litert-lm-api 0.17.0 and 0.17.1 the first row passes and the other two fail: only the first
scoring call after a prefill returns the fresh-session score, and a rewind does not restore it
(google-ai-edge/LiteRT-LM#3561, the proposed fix #3562; the same shape measured on the C API by
kakasolg in #3639). The canary is meant to flip to PASS on the release that carries the fix.

The C API comes from the litert-lm-api wheel's liblitert-lm.dylib, loaded with ctypes (the Python
API has run_text_scoring but no checkpoint calls). By default the wheel pinned in pins.env
(GEN_PYPI_LITERT_LM) is installed into cache/scoring-venv-<version> with uv; --version tries another
release, --dylib points at any build of the library (a source build with the fix, on the day).
Stdlib only, like the other runners.
"""
import argparse
import ctypes
import glob
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from channels_common import CACHE, check, load_pins, resolve_canary, sha256_file, write_result  # noqa: E402

PROMPT = "The capital of France is"
CANDIDATES = [" Paris", " London", " Berlin"]
TEXT = 0  # kLiteRtLmInputDataTypeText, the first enumerator of LiteRtLmInputDataType (c/engine.h)


def find_dylib(venv):
    hits = glob.glob(os.path.join(venv, "lib", "python3*", "site-packages", "litert_lm", "liblitert-lm.dylib"))
    return hits[0] if hits else None


def ensure_wheel(version):
    """Install litert-lm-api==<version> into a venv under cache/ (hermetic; the machine's own
    litert-lm install is not touched) and return the dylib path."""
    venv = os.path.join(CACHE, f"scoring-venv-{version}")
    dylib = find_dylib(venv)
    if dylib:
        return dylib, "cached"
    os.makedirs(CACHE, exist_ok=True)
    subprocess.run(["uv", "venv", "--quiet", venv], check=True)
    py = os.path.join(venv, "bin", "python")
    subprocess.run(["uv", "pip", "install", "--quiet", "--python", py, f"litert-lm-api=={version}"], check=True)
    dylib = find_dylib(venv)
    if not dylib:
        raise RuntimeError(f"litert-lm-api=={version} installed but no liblitert-lm.dylib under {venv}")
    return dylib, "installed"


class CApi:
    """The handful of C API calls this check needs, typed for ctypes."""

    def __init__(self, path):
        L = ctypes.CDLL(path)
        vp, cp, ci, cb, cs, cf = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_bool,
                                  ctypes.c_size_t, ctypes.c_float)
        sig = {
            "litert_lm_engine_settings_create": ([cp, cp, cp, cp], vp),
            "litert_lm_engine_settings_set_cache_dir": ([vp, cp], None),
            "litert_lm_engine_settings_set_max_num_tokens": ([vp, ci], None),
            "litert_lm_engine_settings_delete": ([vp], None),
            "litert_lm_engine_create": ([vp], vp),
            "litert_lm_engine_delete": ([vp], None),
            "litert_lm_session_config_create": ([], vp),
            "litert_lm_session_config_set_apply_prompt_template": ([vp, cb], None),
            "litert_lm_session_config_delete": ([vp], None),
            "litert_lm_engine_create_session": ([vp, vp], vp),
            "litert_lm_session_delete": ([vp], None),
            "litert_lm_input_data_create": ([ci, vp, cs], vp),
            "litert_lm_input_data_delete": ([vp], None),
            "litert_lm_session_run_prefill": ([vp, ctypes.POINTER(vp), cs], ci),
            "litert_lm_session_run_text_scoring": ([vp, ctypes.POINTER(cp), cs, cb], vp),
            "litert_lm_session_save_checkpoint": ([vp, cp], ci),
            "litert_lm_session_rewind_to_checkpoint": ([vp, cp], ci),
            "litert_lm_responses_get_num_candidates": ([vp], ci),
            "litert_lm_responses_has_score_at": ([vp, ci], cb),
            "litert_lm_responses_get_score_at": ([vp, ci], cf),
            "litert_lm_responses_delete": ([vp], None),
        }
        for name, (args, res) in sig.items():
            fn = getattr(L, name)
            fn.argtypes, fn.restype = args, res
        self.L = L

    def engine(self, model, cache_dir, max_tokens=256):
        L = self.L
        st = L.litert_lm_engine_settings_create(model.encode(), b"cpu", None, None)
        if not st:
            raise RuntimeError("engine settings: NULL")
        L.litert_lm_engine_settings_set_cache_dir(st, cache_dir.encode())
        L.litert_lm_engine_settings_set_max_num_tokens(st, max_tokens)
        eng = L.litert_lm_engine_create(st)
        L.litert_lm_engine_settings_delete(st)
        if not eng:
            raise RuntimeError("engine create: NULL")
        return eng

    def session(self, eng):
        L = self.L
        cfg = L.litert_lm_session_config_create()
        L.litert_lm_session_config_set_apply_prompt_template(cfg, False)
        s = L.litert_lm_engine_create_session(eng, cfg)
        L.litert_lm_session_config_delete(cfg)
        if not s:
            raise RuntimeError("session create: NULL")
        return s

    def prefill(self, s, text):
        L = self.L
        raw = text.encode()
        buf = ctypes.create_string_buffer(raw, len(raw))
        inp = L.litert_lm_input_data_create(TEXT, ctypes.cast(buf, ctypes.c_void_p), len(raw))
        if not inp:
            raise RuntimeError("input data: NULL")
        arr = (ctypes.c_void_p * 1)(inp)
        rc = L.litert_lm_session_run_prefill(s, arr, 1)
        L.litert_lm_input_data_delete(inp)
        if rc != 0:
            raise RuntimeError(f"run_prefill rc={rc}")

    def score(self, s, target):
        L = self.L
        arr = (ctypes.c_char_p * 1)(target.encode())
        r = L.litert_lm_session_run_text_scoring(s, arr, 1, False)
        if not r:
            raise RuntimeError("run_text_scoring: NULL")
        try:
            if L.litert_lm_responses_get_num_candidates(r) < 1 or not L.litert_lm_responses_has_score_at(r, 0):
                raise RuntimeError("run_text_scoring: no score")
            return float(L.litert_lm_responses_get_score_at(r, 0))
        finally:
            L.litert_lm_responses_delete(r)


def run(api, model, cache_dir):
    eng = api.engine(model, cache_dir)
    try:
        # fresh arm: one session and one prefill per candidate (the reference)
        fresh = []
        t0 = time.time()
        for c in CANDIDATES:
            s = api.session(eng)
            api.prefill(s, PROMPT)
            fresh.append(api.score(s, c))
            api.L.litert_lm_session_delete(s)
        t_fresh = time.time() - t0
        # shared arm: one prefill, a checkpoint, a scoring call and a rewind per candidate
        s = api.session(eng)
        t0 = time.time()
        api.prefill(s, PROMPT)
        rc_save = api.L.litert_lm_session_save_checkpoint(s, b"q")
        shared, rc_rewind = [], []
        for c in CANDIDATES:
            shared.append(api.score(s, c))
            rc_rewind.append(api.L.litert_lm_session_rewind_to_checkpoint(s, b"q"))
        again = api.score(s, CANDIDATES[0])
        t_shared = time.time() - t0
        api.L.litert_lm_session_delete(s)
        return dict(fresh=fresh, shared=shared, again=again, rc_save=rc_save, rc_rewind=rc_rewind,
                    t_fresh=t_fresh, t_shared=t_shared)
    finally:
        api.L.litert_lm_engine_delete(eng)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="results dir")
    ap.add_argument("--version", help="litert-lm-api wheel version (default: pins.env GEN_PYPI_LITERT_LM)")
    ap.add_argument("--dylib", help="use this liblitert-lm.dylib instead of a wheel (a source build)")
    ap.add_argument("--model", help=".litertlm path (default: the pinned canary)")
    ap.add_argument("--tol", type=float, default=1e-3)
    a = ap.parse_args()
    pins = load_pins()
    version = a.version or pins["GEN_PYPI_LITERT_LM"]
    if a.dylib:
        dylib, src = a.dylib, "given"
        version = f"dylib:{os.path.basename(os.path.dirname(a.dylib))}"
    else:
        dylib, src = ensure_wheel(version)
    if a.model:
        model, msrc = a.model, "given"
    else:
        model, msrc = resolve_canary(pins["CANARY_LLM_REPO"], pins["CANARY_LLM_FILE"])
    cache_dir = os.path.join(CACHE, "scoring-engine-cache")
    os.makedirs(cache_dir, exist_ok=True)
    print(f"[scoring] dylib={dylib} ({src}) model={model} ({msrc}) prompt={PROMPT!r} candidates={CANDIDATES}")
    api = CApi(dylib)
    r = run(api, model, cache_dir)
    f, s = r["fresh"], r["shared"]
    d = [abs(s[i] - f[i]) for i in range(len(CANDIDATES))]
    drift = abs(r["again"] - s[0])
    fmt = lambda xs: ", ".join(f"{x:.4f}" for x in xs)  # noqa: E731
    base = (f"fresh [{fmt(f)}] shared [{fmt(s)}] again {r['again']:.4f}; save rc={r['rc_save']} "
            f"rewind rc={r['rc_rewind']}; {len(CANDIDATES)} scores fresh {r['t_fresh']:.2f}s / shared {r['t_shared']:.2f}s")
    known = "#3561"
    checks = [
        check("scoring.first", "first candidate after the checkpoint = fresh-session score",
              "PASS" if d[0] <= a.tol else "FAIL", f"|Δ|={d[0]:.5f} tol={a.tol}; {base}",
              issue="" if d[0] <= a.tol else known),
        check("scoring.rewind", "every candidate = fresh-session score (rewind_to_checkpoint restores the session)",
              "PASS" if max(d) <= a.tol else "FAIL", f"max|Δ|={max(d):.5f} per candidate [{fmt(d)}] tol={a.tol}",
              issue="" if max(d) <= a.tol else known),
        check("scoring.repeat", "first candidate scored again after the rewinds = its first score",
              "PASS" if drift <= a.tol else "FAIL", f"|Δ|={drift:.5f} tol={a.tol}",
              issue="" if drift <= a.tol else known),
    ]
    write_result("scoring", checks, a.out, extra={
        "runtime": version, "dylib": dylib, "dylib_sha256": sha256_file(dylib)[:16],
        "model": os.path.basename(model), "model_sha256": sha256_file(model)[:16],
        "prompt": PROMPT, "candidates": CANDIDATES, "backend": "cpu", "host": "macOS"})
    return 0 if all(c["status"] == "PASS" for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
