"""Shared plumbing for the release-artifact channel gates.

Stdlib-only on purpose: these runners must work on release day with whatever
python3 the machine has, so no huggingface_hub, no requests, no jsonschema. HF auth comes from ~/.cache/huggingface/token if
present; GitHub auth from `gh auth token` if present. Both optional.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = HERE
CACHE = os.path.join(HERE, "cache")


def load_pins():
    pins = {}
    with open(os.path.join(HERE, "pins.env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                pins[k] = v
    return pins


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def results_dir(explicit=None):
    d = explicit or os.environ.get("CHANNELS_OUT") or os.path.join(
        HERE, "results_" + time.strftime("%Y%m%d"))
    os.makedirs(d, exist_ok=True)
    return d


def check(cid, desc, status, measured="", issue="", evidence=""):
    """One row of the PASS/FAIL table. `issue` names the known upstream issue a
    FAIL matches; a FAIL with no issue is a candidate NEW finding (draft-only)."""
    return {"id": cid, "desc": desc, "status": status, "measured": measured,
            "issue": issue, "evidence": evidence}


def write_result(channel, checks, outdir=None, extra=None):
    outdir = results_dir(outdir)
    rec = {"channel": channel, "generation": load_pins()["GEN_LITERTLM_TAG"],
           "ts": utcnow(), "checks": checks}
    if extra:
        rec.update(extra)
    path = os.path.join(outdir, f"{channel}.json")
    with open(path, "w") as f:
        json.dump(rec, f, indent=1)
    fails = [c for c in checks if c["status"] == "FAIL"]
    print(f"[{channel}] {len(checks)} checks, {len(fails)} FAIL -> {path}")
    for c in checks:
        mark = {"PASS": "ok  ", "FAIL": "FAIL", "SKIP": "skip"}.get(c["status"], "?   ")
        line = f"  [{mark}] {c['id']}: {c['measured'][:110]}"
        if c["status"] == "FAIL":
            line += f"  ({c['issue'] or 'NO KNOWN ISSUE — draft only'})"
        print(line)
    return path


def gh_token():
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True,
                              text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def hf_token():
    p = os.path.expanduser("~/.cache/huggingface/token")
    try:
        return open(p).read().strip() or None
    except Exception:
        return None


def fetch_json(url, token=None, timeout=30):
    headers = {"User-Agent": "release-artifact-gate"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                timeout=timeout) as r:
        return json.load(r)


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def download(url, dest, expected_size=None, token=None, tries=3):
    """curl -C - with a byte-count check. A transfer that exits 0 short of the
    advertised size is recorded as truncated, not trusted (it happens)."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if expected_size and os.path.exists(dest) and os.path.getsize(dest) == expected_size:
        return dest
    cmd = ["curl", "-L", "--retry", "3", "-C", "-", "-o", dest, url]
    if token:
        cmd[1:1] = ["-H", f"Authorization: Bearer {token}"]
    for i in range(tries):
        subprocess.run(cmd, capture_output=True, timeout=3600)
        if os.path.exists(dest):
            if expected_size is None or os.path.getsize(dest) == expected_size:
                return dest
        time.sleep(2)
    got = os.path.getsize(dest) if os.path.exists(dest) else 0
    raise RuntimeError(f"download truncated: {url} got={got} want={expected_size}")


def hf_cached(repo, filename):
    """Path inside ~/.cache/huggingface/hub without importing huggingface_hub."""
    d = os.path.expanduser(f"~/.cache/huggingface/hub/models--{repo.replace('/', '--')}")
    snaps = os.path.join(d, "snapshots")
    if not os.path.isdir(snaps):
        return None
    for snap in sorted(os.listdir(snaps), reverse=True):
        p = os.path.join(snaps, snap, filename)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return os.path.realpath(p)
    return None


def resolve_canary(repo, filename, local_rel=None):
    """(path, source). Local pinned copy first, then HF cache, then download
    into channels/cache/ (never into the HF cache — we do not own its layout)."""
    if local_rel:
        p = os.path.join(REPO, local_rel)
        if os.path.exists(p):
            return p, "local"
    p = hf_cached(repo, filename)
    if p:
        return p, "hf-cache"
    url = f"https://huggingface.co/{repo}/resolve/main/{filename}"
    dest = os.path.join(CACHE, "canary", repo.replace("/", "__"), filename)
    meta = fetch_json(f"https://huggingface.co/api/models/{repo}?blobs=true",
                      token=hf_token())
    size = next((s.get("size") for s in meta.get("siblings", [])
                 if s["rfilename"] == filename), None)
    return download(url, dest, expected_size=size, token=hf_token()), "downloaded"
