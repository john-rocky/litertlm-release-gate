#!/usr/bin/env python3
"""Channel: GitHub release assets — is what the release page hands out complete?

Reads the LiteRT-LM release at GEN_LITERTLM_TAG and the LiteRT release at
GEN_LITERT_TAG, downloads every zip the Swift package manifest or the release
page points at, and checks CONTENT, not existence:

  - Package.swift binary pins: URLs resolve, sha256 matches the declared checksum
    (a SwiftPM user hits exactly these bytes).
  - xcframework zips: capabilities C API present? (#2529 -> fix PR #3273 moved it
    to c/ and packaged it; merged AFTER v0.16.1 was cut, so the current
    generation is expected to still lack it -- measure, don't assume).
  - xcframework zips: NOTICE / SBOM inside the artifact (#3194 asked for
    binary-specific ones; release-level files appeared in v0.16.0).
  - litert_lm_c_api zip: header inventory + capabilities.h.
  - LiteRT NPU runtime zips: qualcomm/samsung/mediatek vendor dirs (#9482).
  - Every zip: no zero-byte members that look like binaries.

Read-only against GitHub; downloads cached in channels/cache/.
"""
import argparse
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from channels_common import (CACHE, check, download, fetch_json, gh_token,  # noqa: E402
                             load_pins, sha256_file, write_result)

API = "https://api.github.com/repos"


def release_assets(repo, tag, token):
    d = fetch_json(f"{API}/{repo}/releases/tags/{tag}", token=token)
    return {a["name"]: a for a in d["assets"]}


def swiftpm_pins(repo, tag, token):
    """(url, checksum) pairs from Package.swift binaryTargets at `tag`."""
    import base64
    d = fetch_json(f"{API}/{repo}/contents/Package.swift?ref={tag}", token=token)
    text = base64.b64decode(d["content"]).decode()
    pins = []
    for m in re.finditer(r'url:\s*\n?\s*"([^"]+)"\s*,\s*\n?\s*checksum:\s*"([a-f0-9]{64})"',
                         text):
        pins.append((m.group(1), m.group(2)))
    return pins, text


def zip_names(path):
    with zipfile.ZipFile(path) as z:
        return [(i.filename, i.file_size) for i in z.infolist()]


def grep_names(names, pattern):
    rx = re.compile(pattern, re.IGNORECASE)
    return [n for n, _ in names if rx.search(n)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out")
    args = ap.parse_args()
    pins = load_pins()
    token = gh_token()
    lm_tag, rt_tag = pins["GEN_LITERTLM_TAG"], pins["GEN_LITERT_TAG"]
    checks = []

    # ------------------------------------------------ LiteRT-LM release inventory
    lm_assets = release_assets("google-ai-edge/LiteRT-LM", lm_tag, token)
    inv = ", ".join(sorted(lm_assets)) or "(none)"
    checks.append(check("ghlm.inventory", f"assets on LiteRT-LM {lm_tag}", "PASS",
                        f"{len(lm_assets)}: {inv}"))

    has_notice = any(re.search(r"NOTICE|spdx", n, re.I) for n in lm_assets)
    checks.append(check(
        "ghlm.release-license-docs",
        f"SBOM/THIRD_PARTY_NOTICES published beside the {lm_tag} binaries",
        "PASS" if has_notice else "FAIL",
        f"{lm_tag} assets carry NOTICE/SBOM: {has_notice}",
        issue="" if has_notice else "LiteRT-LM#3194",
        evidence=f"release {lm_tag} asset list"))

    # ------------------------------------------------ SwiftPM binary pins
    spm, _ = swiftpm_pins("google-ai-edge/LiteRT-LM", lm_tag, token)
    if not spm:
        checks.append(check("ghlm.swiftpm-pins", "binaryTarget pins in Package.swift",
                            "FAIL", "no url/checksum pairs parsed", issue=""))
    hosted_tags = set()
    xcf_paths = {}
    for url, want in spm:
        name = url.rsplit("/", 1)[1]
        m = re.search(r"/download/([^/]+)/", url)
        hosted_tags.add(m.group(1) if m else "?")
        # asset size for the truncation check comes from the hosting release
        host_assets = release_assets("google-ai-edge/LiteRT-LM", m.group(1), token) if m else {}
        size = host_assets.get(name, {}).get("size")
        dest = os.path.join(CACHE, "ghlm", name)
        try:
            download(url, dest, expected_size=size)
            got = sha256_file(dest)
            ok = got == want
            checks.append(check(
                f"ghlm.swiftpm-checksum.{name}",
                "downloaded zip sha256 == Package.swift checksum",
                "PASS" if ok else "FAIL",
                f"{name}: sha256 {'matches' if ok else f'MISMATCH got={got[:16]} want={want[:16]}'}",
                issue="",
                evidence=url))
            if ok:
                xcf_paths[name] = dest
        except Exception as e:
            checks.append(check(f"ghlm.swiftpm-fetch.{name}", "pinned binary URL resolves",
                                "FAIL", f"{type(e).__name__}: {e}"[:160], issue="",
                                evidence=url))
    if hosted_tags:
        lag = hosted_tags != {lm_tag}
        checks.append(check(
            "ghlm.swiftpm-binary-lag",
            f"Package.swift@{lm_tag} points its binaries at",
            "PASS",  # informational: recorded, judged in the table notes
            f"hosted on {sorted(hosted_tags)}"
            + (f" (tag is {lm_tag}: binaries lag the tag)" if lag else "")))

    # ------------------------------------------------ xcframework content checks
    for name, path in sorted(xcf_paths.items()):
        names = zip_names(path)
        cap = grep_names(names, r"capabilit")
        checks.append(check(
            f"ghlm.xcf-capabilities.{name}",
            "capabilities C API packaged in the xcframework (#2529, fix=PR#3273)",
            "PASS" if cap else "FAIL",
            f"{len(cap)} member(s) matching 'capabilit'" + (f": {cap[:3]}" if cap else ""),
            issue="" if cap else "LiteRT-LM#2529 (fix PR#3273 merged 08-18, after v0.16.1)",
            evidence=f"unzip -l {os.path.basename(path)}"))
        lic = grep_names(names, r"NOTICE|THIRD_PARTY|spdx|LICENSE")
        checks.append(check(
            f"ghlm.xcf-notices.{name}",
            "NOTICE/SBOM inside the xcframework zip (#3194 binary-specific ask)",
            "PASS" if lic else "FAIL",
            f"license/SBOM members: {lic[:4] if lic else 'none'}",
            issue="" if lic else "LiteRT-LM#3194",
            evidence=f"unzip -l {os.path.basename(path)}"))
        empties = [n for n, s in names
                   if s == 0 and not n.endswith("/") and re.search(r"\.(h|dylib|a)$|/[^./]+$", n)]
        checks.append(check(
            f"ghlm.xcf-nonempty.{name}", "no zero-byte binaries/headers in the zip",
            "PASS" if not empties else "FAIL",
            "all members non-empty" if not empties else f"zero-byte: {empties[:5]}",
            issue=""))

    # ------------------------------------------------ C API zip (hosts on the binary tag)
    c_api = None
    for tag in [lm_tag, *sorted(hosted_tags, reverse=True)]:
        try:
            assets = release_assets("google-ai-edge/LiteRT-LM", tag, token)
        except Exception:
            continue
        hit = next((a for n, a in assets.items() if n.startswith("litert_lm_c_api")), None)
        if hit:
            c_api = (tag, hit)
            break
    if c_api:
        tag, a = c_api
        dest = os.path.join(CACHE, "ghlm", a["name"])
        download(a["browser_download_url"], dest, expected_size=a["size"])
        names = zip_names(dest)
        hdrs = grep_names(names, r"\.h$")
        cap = grep_names(names, r"capabilit")
        libs = grep_names(names, r"\.(dylib|so|a|dll|lib)$")
        checks.append(check(
            "ghlm.c-api-zip", f"{a['name']} (hosted on {tag}) header/lib inventory",
            "PASS" if hdrs and libs else "FAIL",
            f"{len(hdrs)} headers, {len(libs)} libs, capabilities members: {len(cap)}",
            issue="", evidence=f"unzip -l {a['name']}"))
        checks.append(check(
            "ghlm.c-api-capabilities",
            "capabilities C API in the prebuilt C zip (#2529, fix=PR#3273)",
            "PASS" if cap else "FAIL",
            f"members matching 'capabilit': {cap[:3] if cap else 'none'}",
            issue="" if cap else "LiteRT-LM#2529 (fix PR#3273 merged 08-18, after v0.16.1)",
            evidence=f"unzip -l {a['name']}"))
    else:
        checks.append(check("ghlm.c-api-zip", "prebuilt C API zip on the release",
                            "FAIL", "no litert_lm_c_api*.zip on the generation's releases",
                            issue=""))

    # ------------------------------------------------ LiteRT NPU runtime zips (#9482)
    rt_assets = release_assets("google-ai-edge/LiteRT", rt_tag, token)
    checks.append(check("ghrt.inventory", f"assets on LiteRT {rt_tag}", "PASS",
                        ", ".join(f"{n} ({a['size']//1024}KB)" for n, a in sorted(rt_assets.items()))))
    for name, a in sorted(rt_assets.items()):
        dest = os.path.join(CACHE, "ghrt", name)
        download(a["browser_download_url"], dest, expected_size=a["size"])
        names = zip_names(dest)
        if "npu" in name:
            vendors = {v: bool(grep_names(names, v)) for v in ("qualcomm", "samsung", "mediatek")}
            missing = [v for v, ok in vendors.items() if not ok]
            checks.append(check(
                f"ghrt.npu-vendors.{name}",
                "vendor runtime dirs inside the NPU zip (#9482)",
                "PASS" if not missing else "FAIL",
                f"present: {[v for v, ok in vendors.items() if ok]}, missing: {missing}",
                issue="" if not missing else "LiteRT#9482",
                evidence=f"unzip -l {name}"))
        else:
            top = sorted({n.split("/")[0] for n, _ in names})
            checks.append(check(
                f"ghrt.manifest.{name}", "zip content inventory",
                "PASS", f"{len(names)} members, top-level: {top[:8]}",
                evidence=f"unzip -l {name}"))

    write_result("gh_assets", checks, args.out,
                 extra={"litertlm_tag": lm_tag, "litert_tag": rt_tag})
    return 1 if any(c["status"] == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
