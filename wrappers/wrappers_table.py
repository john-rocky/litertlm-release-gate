#!/usr/bin/env python3
"""The LiteRT-LM version each downstream wrapper pins, as one table.

    python3 wrappers/wrappers_table.py

Reads wrappers/wrappers.json and writes wrappers/TABLE.md (markdown) and
wrappers/table.json (the same rows, for diffing one release against the next).

Each pin is read from the wrapper's default branch HEAD (or the entry's "ref")
through the GitHub contents API, so every location links to a commit sha.
Latest versions come from the GitHub releases of google-ai-edge/LiteRT-LM,
Google Maven's maven-metadata.xml and the npm registry. Open pull requests and
issues whose title names LiteRT-LM together with a version move are listed
from the GitHub issues API.

Entry fields (wrappers.json):
  repo        owner/name on GitHub (required)
  ecosystem   grouping label; rows sort by ecosystem, then name
  name, url   display name and link, when the row is not the repo itself
  ref         branch or tag to read instead of the default branch
  kind        "library" (default) or "app"; own: true for the author's repos
  package     {"registry": "npm" | "pub" | "crates" | "nuget", "name": ...}
  pins        list of {platform, channel, ...}; channel is one of
                maven        version from Google Maven litertlm-android
                xcframework  GitHub release tag that ships CLiteRTLM.xcframework.zip
                github       any GitHub release tag (C API, source builds)
                npm          @litert-lm/core version
                none / unverified   no readable version; "text" is shown
              plus either {path, regex with a (?P<v>...) group, optional
              "after" regex that must match on an earlier line} or
              {submodule: path of a git submodule of LiteRT-LM}
  notes_in_repo  list of {path, regex, label}: a line in the repository that
              says something about the pinned version (linked in the last column)
  note, links free text and [label, url] pairs printed under the table

Stdlib only. GitHub is read through `gh api` when gh is installed and logged
in, otherwise over HTTPS with GITHUB_TOKEN (or GH_TOKEN) when set.
Exit status 1 when a configured pin no longer matches; that cell then reads
"unverified" and the entry's path or pattern needs an update.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "litertlm-release-gate-wrappers-table"
VER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(.*)$")
STABLE = re.compile(r"^v?\d+\.\d+\.\d+$")
NAMES_LITERTLM = re.compile(r"litert[-_ ]?lm|litertlm", re.I)
MOVES_VERSION = re.compile(r"\b(bump|update|upgrade|re-?pin|released)\b|\bto v?\d+\.\d+", re.I)
CHANNEL_LABEL = {"maven": "Maven", "xcframework": "GitHub, xcframework", "github": "GitHub", "npm": "npm"}


class FetchError(Exception):
    pass


def vkey(s):
    """Sort key: (major, minor, patch, 1 for a release / 0 for a pre-release)."""
    m = VER.match((s or "").strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if m.group(4) else 1)


def http_get(url, headers=None, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise FetchError(f"{url}: HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise FetchError(f"{url}: {e.reason}") from None
    return body if raw else json.loads(body)


class GitHub:
    def __init__(self):
        self.use_gh = (shutil.which("gh") is not None
                       and subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0)
        self.token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not self.use_gh and not self.token:
            print("warn: no gh login and no GITHUB_TOKEN; the unauthenticated limit (60/h) is too low "
                  "for a full table", file=sys.stderr)

    def get(self, path, raw=False):
        if self.use_gh:
            args = ["gh", "api", path] + (["-H", "Accept: application/vnd.github.raw"] if raw else [])
            p = subprocess.run(args, capture_output=True)
            if p.returncode != 0:
                raise FetchError(f"gh api {path}: {p.stderr.decode(errors='replace').strip()[:200]}")
            return p.stdout if raw else json.loads(p.stdout)
        headers = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return http_get("https://api.github.com/" + path.lstrip("/"), headers, raw)

    def pages(self, path, max_pages=10):
        out, sep = [], "&" if "?" in path else "?"
        for page in range(1, max_pages + 1):
            items = self.get(f"{path}{sep}per_page=100&page={page}")
            out += items
            if len(items) < 100:
                break
        return out


def read_upstream(gh, up, need_npm):
    rels = [r for r in gh.pages(f"repos/{up['github']}/releases") if not r["draft"]]
    stable = [r for r in rels if not r["prerelease"] and vkey(r["tag_name"])]
    stable.sort(key=lambda r: vkey(r["tag_name"]))
    asset = up["xcframework_asset"]
    tags_by_sha = {}
    for t in gh.pages(f"repos/{up['github']}/tags"):
        tags_by_sha.setdefault(t["commit"]["sha"], []).append(t["name"])
    root = ET.fromstring(http_get(up["maven_metadata"], raw=True))
    maven = sorted({v.text.strip() for v in root.iter("version") if STABLE.match(v.text.strip())}, key=vkey)
    out = {
        "github": {
            "repo": up["github"],
            "stable": [r["tag_name"] for r in stable],
            "with_xcframework": [r["tag_name"] for r in stable if any(a["name"] == asset for a in r["assets"])],
            "published": {r["tag_name"]: r["published_at"][:10] for r in stable},
        },
        "maven": {"coordinate": up["maven_coordinate"], "stable": maven},
        "tags_by_sha": tags_by_sha,
    }
    if need_npm:
        d = http_get("https://registry.npmjs.org/" + urllib.parse.quote(up["npm"], safe="@"))
        vers = d["versions"]
        out["npm"] = {"package": up["npm"],
                      "stable": sorted([v for v in vers if STABLE.match(v) and not vers[v].get("deprecated")],
                                       key=vkey),
                      "deprecated": sorted([v for v in vers if vers[v].get("deprecated")],
                                           key=lambda v: vkey(v) or (0, 0, 0, 0)),
                      "dist_tags": d.get("dist-tags", {})}
    return out


def channel_versions(upstream, channel):
    if channel == "maven":
        return upstream["maven"]["stable"]
    if channel == "xcframework":
        return upstream["github"]["with_xcframework"]
    if channel == "npm":
        return upstream["npm"]["stable"]
    return upstream["github"]["stable"]


class Row:
    """Everything read for one wrapper entry."""

    def __init__(self, gh, upstream, entry, repo_cache, lock):
        self.gh, self.up, self.e = gh, upstream, entry
        self.errors = []
        with lock:
            meta = repo_cache.get(entry["repo"])
        if meta is None:
            meta = gh.get(f"repos/{entry['repo']}")
            with lock:
                repo_cache[entry["repo"]] = meta
        self.meta = meta
        self.full = meta["full_name"]
        self.ref = entry.get("ref") or meta["default_branch"]
        commit = gh.get(f"repos/{self.full}/commits/{urllib.parse.quote(self.ref, safe='')}")
        self.sha = commit["sha"]
        if entry.get("ref"):
            refs = gh.get(f"repos/{self.full}/git/matching-refs/tags/{urllib.parse.quote(self.ref, safe='')}")
            kind = "tag" if any(r["ref"] == f"refs/tags/{self.ref}" for r in refs) else "branch"
            self.last_push = commit["commit"]["committer"]["date"][:10] + f" ({kind} {self.ref})"
        else:
            self.last_push = meta["pushed_at"][:10]
        self.files = {}

    def text(self, path):
        if path not in self.files:
            body = self.gh.get(f"repos/{self.full}/contents/{urllib.parse.quote(path)}?ref={self.sha}", raw=True)
            self.files[path] = body.decode("utf-8", "replace").splitlines()
        return self.files[path]

    def find(self, path, regex, after=None):
        lines = self.text(path)
        start = 0
        if after:
            hit = next((i for i, l in enumerate(lines) if re.search(after, l)), None)
            if hit is None:
                raise FetchError(f"{path}: no line matches {after!r}")
            start = hit
        rx = re.compile(regex)
        for i in range(start, len(lines)):
            m = rx.search(lines[i])
            if m:
                return i + 1, lines[i].strip(), m
        raise FetchError(f"{path}: no line matches {regex!r}")

    def blob_url(self, path, line=None):
        return f"https://github.com/{self.full}/blob/{self.sha}/{urllib.parse.quote(path)}" + (f"#L{line}" if line else "")

    def pin(self, spec):
        ch = spec["channel"]
        out = {"platform": spec["platform"], "channel": ch, "version": None, "latest": None,
               "newer": None, "newer_versions": [], "how": None, "path": spec.get("path"),
               "line": None, "url": None, "text": spec.get("text")}
        try:
            if spec.get("submodule"):
                self.submodule(spec, out)
            elif spec.get("path") and spec.get("regex"):
                line, text, m = self.find(spec["path"], spec["regex"], spec.get("after"))
                out.update(line=line, url=self.blob_url(spec["path"], line), line_text=text)
                if "v" in m.groupdict():
                    out["version"] = m.group("v")
            elif spec.get("path"):
                self.text(spec["path"])
                out["url"] = self.blob_url(spec["path"])
        except FetchError as err:
            self.errors.append(str(err))
            out["text"] = "unverified (" + str(err)[:120] + ")"
            out["version"] = None
            ch = out["channel"] = "unverified"
        if ch in CHANNEL_LABEL:
            versions = channel_versions(self.up, ch)
            out["latest"] = versions[-1] if versions else None
            if out["version"]:
                key = vkey(out["version"])
                if key is None:
                    self.errors.append(f"{spec['platform']}: cannot read {out['version']!r} as a version")
                else:
                    out["newer_versions"] = [v for v in versions if vkey(v) > key]
                    out["newer"] = len(out["newer_versions"])
        else:
            gh_stable = self.up["github"]["stable"]
            out["latest"] = gh_stable[-1] if gh_stable else None
        return out

    def submodule(self, spec, out):
        info = self.gh.get(f"repos/{self.full}/contents/{urllib.parse.quote(spec['submodule'])}?ref={self.sha}")
        if info.get("type") != "submodule":
            raise FetchError(f"{spec['submodule']} is not a submodule at {self.sha[:7]}")
        sub_sha = info["sha"]
        m = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?/?$", info.get("submodule_git_url") or "")
        sub_repo = m.group(1) if m else self.up["github"]["repo"]
        # GitHub serves no page at /tree/<sha>/<submodule path>: link the parent directory, which lists
        # the submodule with its commit, and the submodule commit in its own repository.
        parent = spec["submodule"].rsplit("/", 1)[0] if "/" in spec["submodule"] else ""
        out.update(submodule_repo=sub_repo, submodule_sha=sub_sha, path=spec["submodule"],
                   url=f"https://github.com/{self.full}/tree/{self.sha}" + (f"/{urllib.parse.quote(parent)}" if parent else ""),
                   submodule_url=f"https://github.com/{sub_repo}/tree/{sub_sha}")
        tags = [t for t in self.up["tags_by_sha"].get(sub_sha, []) if STABLE.match(t)]
        if tags:
            out["version"] = max(tags, key=vkey)
            out["how"] = f"submodule at the {out['version']} tag commit"
            return
        body = self.gh.get(f"repos/{sub_repo}/contents/version.bzl?ref={sub_sha}", raw=True).decode()
        vm = re.search(r'^VERSION\s*=\s*"([^"]+)"', body, re.M)
        if not vm:
            raise FetchError(f"no VERSION in {sub_repo}/version.bzl at {sub_sha[:7]}")
        out["version"] = "v" + vm.group(1)
        out["how"] = f"submodule at {sub_repo}@{sub_sha[:7]}, VERSION in version.bzl"

    def bump_items(self):
        try:
            items = self.gh.pages(f"repos/{self.full}/issues?state=open", max_pages=5)
        except FetchError as err:
            self.errors.append(str(err))
            return None
        found = []
        for it in items:
            t = it["title"]
            if NAMES_LITERTLM.search(t) and MOVES_VERSION.search(t):
                found.append({"type": "PR" if it.get("pull_request") else "issue", "number": it["number"],
                              "url": it["html_url"], "user": it["user"]["login"],
                              "created": it["created_at"][:10], "title": t})
        return sorted(found, key=lambda x: x["number"])

    def notes_in_repo(self):
        out = []
        for r in self.e.get("notes_in_repo", []):
            try:
                line, text, _ = self.find(r["path"], r["regex"])
            except FetchError as err:
                self.errors.append(str(err))
                continue
            out.append({"label": r["label"], "url": self.blob_url(r["path"], line), "line_text": text})
        return out


def downloads(pkg, today):
    if not pkg:
        return {"registry": None, "count": None}
    reg, name = pkg["registry"], pkg["name"]
    out = {"registry": reg, "name": name, "count": None}
    try:
        if reg == "npm":
            d = http_get("https://api.npmjs.org/downloads/point/last-month/" + urllib.parse.quote(name, safe="@"))
            out.update(count=d["downloads"], period=f"{d['start']}..{d['end']}")
        elif reg == "pub":
            d = http_get(f"https://pub.dev/api/packages/{name}/score")
            out.update(count=d.get("downloadCount30Days"), period="30 days")
        elif reg == "crates":
            d = http_get(f"https://crates.io/api/v1/crates/{name}/downloads")
            first, last = (today - timedelta(days=30)).isoformat(), (today - timedelta(days=1)).isoformat()
            rows = d.get("version_downloads", []) + d.get("meta", {}).get("extra_downloads", [])
            out.update(count=sum(r["downloads"] for r in rows if first <= r["date"] <= last), period=f"{first}..{last}")
        elif reg == "nuget":
            # semVerLevel=2.0.0: without it the search leaves out packages with SemVer 2 versions
            d = http_get(f"https://azuresearch-usnc.nuget.org/query?q=packageid:{urllib.parse.quote(name)}"
                         "&prerelease=true&semVerLevel=2.0.0")
            hit = next((x for x in d.get("data", []) if x["id"].lower() == name.lower()), None)
            out.update(total=hit and hit.get("totalDownloads"), period="no monthly count")
    except (FetchError, KeyError, ValueError) as err:
        out["error"] = str(err)[:160]
    return out


def read_row(gh, upstream, entry, repo_cache, lock, today):
    try:
        row = Row(gh, upstream, entry, repo_cache, lock)
    except FetchError as err:
        return {"repo": entry["repo"], "errors": [str(err)], "fatal": True, "entry": entry}
    pins = [row.pin(p) for p in entry["pins"]]
    return {
        "repo": row.full,
        "repo_as_configured": entry["repo"],
        "name": entry.get("name") or row.full,
        "url": entry.get("url") or row.meta["html_url"],
        "ecosystem": entry.get("ecosystem", ""),
        "kind": entry.get("kind", "library"),
        "own": bool(entry.get("own")),
        "archived": row.meta.get("archived", False),
        "ref": row.ref,
        "sha": row.sha,
        "last_push": row.last_push,
        "pins": pins,
        "downloads": downloads(entry.get("package"), today),
        "bump_items": row.bump_items(),
        "notes_in_repo": row.notes_in_repo(),
        "note": entry.get("note"),
        "links": entry.get("links", []),
        "read_date": today.isoformat(),
        "errors": row.errors,
    }


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def fmt_count(n):
    return f"{n:,}"


def render_md(data):
    up, rows, date = data["upstream"], data["rows"], data["read_date"]
    gh_latest = up["github"]["stable"][-1]
    xc_latest = up["github"]["with_xcframework"][-1]
    lines = [
        "# LiteRT-LM versions pinned by downstream wrappers and apps",
        "",
        f"Read {date} (UTC) by `python3 wrappers/wrappers_table.py` from [wrappers.json](wrappers.json); "
        f"the same rows as JSON: [table.json](table.json). Each pin is read at the head of the repository's "
        f"default branch (one row at a tag). A package release already on a registry can carry a different pin.",
        "",
        f"Latest LiteRT-LM on {date}: Google Maven `{up['maven']['coordinate']}` {up['maven']['stable'][-1]} · "
        f"GitHub release {gh_latest} ({up['github']['published'][gh_latest]})"
        + (f", the newest with `CLiteRTLM.xcframework.zip`: {xc_latest}" if xc_latest != gh_latest else
           ", ships `CLiteRTLM.xcframework.zip`")
        + (f" · npm `{up['npm']['package']}` {up['npm']['stable'][-1]}" if "npm" in up else "") + ".",
        "",
        "Newer releases = stable LiteRT-LM versions newer than the pin, counted on the channel named in the "
        "Latest column: (Maven) Google Maven `litertlm-android` versions without a pre-release suffix; "
        "(GitHub, xcframework) GitHub releases not marked pre-release that ship `CLiteRTLM.xcframework.zip`; "
        "(GitHub) all GitHub releases not marked pre-release, used for C API, native-library, source and "
        "submodule pins; (npm) npm `@litert-lm/core` versions without a pre-release suffix and not deprecated.",
        "",
        "Pin prefixes: Android = Maven AAR, iOS = xcframework, C API = prebuilt C library, native = libraries "
        "the wrapper builds or repackages, source = git submodule, Web = npm, Win64 = Windows libraries "
        "vendored in the repo. \"unverified\" = the repo names no version the script can read.",
        "",
        "Downloads / month: npm last-month, pub.dev 30-day count, crates.io last 30 full days, each for the "
        "whole package; \"—\" = no package on npm, pub.dev or crates.io. Other registries are not read: Maven "
        "Central, SwiftPM and Go modules publish no count, JitPack and OpenUPM are not queried, NuGet gives a "
        "total only (in parentheses).",
        "",
        "Last push = GitHub pushed_at (any branch); for the row read at a tag, the date of the tagged commit.",
        "",
        "| Wrapper | LiteRT-LM pin | Latest | Newer releases | Downloads / month | Pin location | Last push "
        "| Open PR or issue on the LiteRT-LM version · note in the repo | Read |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    notes = []
    for r in rows:
        if r.get("fatal"):
            lines.append(f"| {cell(r['repo'])} | unverified | unverified | unverified | unverified | unverified "
                         f"| unverified | unverified | {date} |")
            continue
        tags = [r["ecosystem"]] if r["ecosystem"] else []
        if r["kind"] == "app" and "app" not in r["ecosystem"].lower():
            tags.append("app")
        if r["own"]:
            tags.append("by this table's author")
        if r["archived"]:
            tags.append("archived")
        d = r["downloads"]
        if d.get("registry") in ("npm", "pub", "crates"):
            label = {"npm": "npm", "pub": "pub.dev", "crates": "crates.io"}[d["registry"]]
            pkg = f"{label} `{d['name']}`"
            dl = f"{fmt_count(d['count'])} ({label})" if d.get("count") is not None else "unverified"
        elif d.get("registry") == "nuget":
            pkg = f"NuGet `{d['name']}`"
            dl = f"— (NuGet total {fmt_count(d['total'])})" if d.get("total") is not None else "—"
        else:
            pkg, dl = None, "—"
        wrapper = f"[{r['name']}]({r['url']})<br>{' · '.join(tags)}" + (f" · {pkg}" if pkg else "")
        pin_c, latest_c, newer_c, loc_c = [], [], [], []
        for p in r["pins"]:
            if p["channel"] in CHANNEL_LABEL and p["version"]:
                pin_c.append(f"{p['platform']} {p['version']}" + (f" ({p['how']})" if p.get("how") else ""))
            else:
                pin_c.append(f"{p['platform']} {p['text'] or 'unverified'}")
            ch = p["channel"] if p["channel"] in CHANNEL_LABEL else "github"
            latest_c.append(f"{p['latest']} ({CHANNEL_LABEL[ch]})" if p["latest"] else "unverified")
            if p["newer"] is not None:
                newer_c.append(str(p["newer"]))
            elif p["channel"] == "none":
                newer_c.append("n/a (no pin)")
            else:
                newer_c.append("unverified")
            if p.get("url"):
                where = p["path"] + (f"#L{p['line']}" if p.get("line") else "")
                extra = (f" (submodule → [{p['submodule_sha'][:7]}]({p['submodule_url']}))"
                         if p.get("submodule_sha") else "")
                loc_c.append(f"[{where}]({p['url']}) @ {r['sha'][:7]}{extra}")
            else:
                loc_c.append("unverified")
        bump = []
        for it in r["bump_items"] or []:
            bump.append(f"[{it['type']} #{it['number']}]({it['url']}) {it['user']}, opened {it['created']}: "
                        f"{cell(it['title'])}")
        for n in r.get("notes_in_repo") or []:
            bump.append(f"[{cell(n['label'])}]({n['url']})")
        if r["bump_items"] is None:
            bump.append("unverified")
        bump_c = "<br>".join(bump) if bump else "none found"
        lines.append("| " + " | ".join([
            wrapper, "<br>".join(map(cell, pin_c)), "<br>".join(latest_c), "<br>".join(newer_c), dl,
            "<br>".join(loc_c), cell(r["last_push"]), bump_c, r["read_date"]]) + " |")
        if r.get("note") or r.get("links"):
            links = " ".join(f"[{cell(lbl)}]({url})" for lbl, url in r.get("links", []))
            notes.append(f"- **{r['name']}**: {r.get('note') or ''} {links}".rstrip())
    if notes:
        lines += ["", "Notes:", ""] + notes
    lines += ["", "Open PRs and issues: open items whose title names LiteRT-LM and a version move (bump, update, "
                  "upgrade, re-pin, released, \"to vX.Y\"), read from the GitHub issues API. \"none found\" = no open "
                  "title matched and no note on the pin was found in the README or next to the pin line.", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(HERE, "wrappers.json"))
    ap.add_argument("--md", default=os.path.join(HERE, "TABLE.md"))
    ap.add_argument("--json", default=os.path.join(HERE, "table.json"))
    ap.add_argument("--jobs", type=int, default=6)
    args = ap.parse_args()

    cfg = json.load(open(args.config))
    today = datetime.now(timezone.utc).date()
    gh = GitHub()
    need_npm = any(p["channel"] == "npm" for w in cfg["wrappers"] for p in w["pins"])
    upstream = read_upstream(gh, cfg["upstream"], need_npm)
    cache, lock = {}, threading.Lock()
    with ThreadPoolExecutor(args.jobs) as ex:
        rows = list(ex.map(lambda e: read_row(gh, upstream, e, cache, lock, today), cfg["wrappers"]))
    rows.sort(key=lambda r: (r.get("ecosystem", "").lower(), r.get("name", r["repo"]).lower(), r["repo"].lower()))
    up_out = {k: v for k, v in upstream.items() if k != "tags_by_sha"}
    data = {"generated_by": "wrappers/wrappers_table.py", "read_date": today.isoformat(),
            "upstream": up_out, "rows": rows}
    with open(args.json, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    with open(args.md, "w") as f:
        f.write(render_md(data))
    bad = [(r["repo"], e) for r in rows for e in r.get("errors", [])]
    for repo, err in bad:
        print(f"unverified: {repo}: {err}", file=sys.stderr)
    print(f"{len(rows)} rows -> {os.path.relpath(args.md)}, {os.path.relpath(args.json)}"
          + (f"; {len(bad)} unverified" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
