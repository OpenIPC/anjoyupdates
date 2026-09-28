#!/usr/bin/env python3
"""Archive Anjoy Vision's firmware builds as release assets.

  GH_TOKEN=... python download_firmwares.py [--max-per-run N] [--commit-every N] [--dry-run]

For every row of items.json (refresh.py) not yet in archive/index.json, the
build is fetched from Anjoy's Aliyun OSS bucket, checked against the MD5 and
size the list gives, and uploaded to this repository's "firmware-archive"
release as r<RID>__<file name>. A file two rows share (80 of them do) is
uploaded once and both rows point at it.

Outcomes, in archive/index.json keyed "r<RID>":
  revisions[]    archived: asset_url, sha256, md5, size, archived_at
  unavailable[]  the bucket answers 403/404/410 for the file
A download whose MD5 or size disagrees with the list is a transient failure:
nothing is recorded and the row is tried again next run.

Without --dry-run this uploads to the real release and commits and pushes
archive/index.json itself (every --commit-every successes).
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent
ITEMS = ROOT / "items.json"
INDEX_PATH = ROOT / "archive" / "index.json"
RELEASE_TAG = "firmware-archive"
BUCKET = "https://ossfiles002.oss-cn-shanghai.aliyuncs.com/"
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/128.0 Safari/537.36"}


class Unavailable(Exception):
    """The bucket no longer has the file."""


def safe_token(value):
    cleaned = SAFE_NAME_RE.sub("_", (value or "").strip()).strip("._-")
    return cleaned or "unknown"


def load_index():
    if INDEX_PATH.exists():
        with INDEX_PATH.open() as f:
            return json.load(f)
    return {}


def save_index(index):
    INDEX_PATH.parent.mkdir(exist_ok=True)
    tmp = INDEX_PATH.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(index, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(INDEX_PATH)


def file_url(row):
    """The build on Anjoy's bucket, as its download page links it."""
    return BUCKET + quote(row["UpFile"].strip(), safe="/")


def pending_rows(index, rows):
    """Rows not archived yet, nor recorded as gone with the same file."""
    out = []
    for row in rows:
        entry = index.get(f"r{row['RID']}") or {}
        md5 = row["FMD5"].strip().lower()
        if any(r.get("md5") == md5 for r in entry.get("revisions", [])):
            continue
        if any(r.get("md5") == md5 for r in entry.get("unavailable", [])):
            continue
        out.append(row)
    return out


def download(url, dest):
    md5, sha, size = hashlib.md5(), hashlib.sha256(), 0
    with requests.get(url, headers=HEADERS, stream=True, timeout=300) as r:
        if r.status_code in (403, 404, 410):
            raise Unavailable(f"bucket answered {r.status_code}")
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                md5.update(chunk)
                sha.update(chunk)
                size += len(chunk)
    return md5.hexdigest(), sha.hexdigest(), size


def gh(*args, check=True, capture=False):
    return subprocess.run(["gh", *args], check=check, capture_output=capture, text=True)


def ensure_release_exists():
    if gh("release", "view", RELEASE_TAG, check=False, capture=True).returncode == 0:
        return
    gh("release", "create", RELEASE_TAG, "--title", "Firmware archive",
       "--notes", "Mirror of Anjoy Vision's firmware builds. See archive/index.json for each build's row and asset.")


def existing_release_assets():
    """Asset name -> sha256 ("" when GitHub reports none)."""
    res = gh("release", "view", RELEASE_TAG, "--json", "assets", check=False, capture=True)
    if res.returncode != 0:
        raise RuntimeError(f"cannot list {RELEASE_TAG} assets: {res.stderr.strip()}")
    return {a["name"]: (a.get("digest") or "").removeprefix("sha256:") for a in json.loads(res.stdout).get("assets", [])}


def repo_slug():
    if slug := os.environ.get("GITHUB_REPOSITORY"):
        return slug
    res = gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner", check=False, capture=True)
    return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else "OpenIPC/anjoyupdates"


def git(*args, check=True):
    return subprocess.run(["git", *args], check=check, cwd=ROOT, capture_output=True, text=True)


def commit_and_push(count):
    git("add", str(INDEX_PATH.relative_to(ROOT)))
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    git("commit", "-m", f"archive: +{count} firmware builds")
    git("push", check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-per-run", type=int, default=100)
    ap.add_argument("--commit-every", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rows = json.load(ITEMS.open())["rows"]
    index = load_index()
    pending = pending_rows(index, rows)
    if args.max_per_run > 0:
        pending = pending[: args.max_per_run]
    if not pending:
        print("Nothing to download -- the archive is up to date.")
        return 0
    if not args.dry_run:
        ensure_release_exists()
    try:
        assets = existing_release_assets()
    except RuntimeError as e:
        if not args.dry_run:
            print(f"Aborting: {e}", file=sys.stderr)
            return 1
        assets = {}
    by_sha = {sha: name for name, sha in assets.items() if sha}
    slug = repo_slug()
    now = lambda: dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    done = failures = gone = since = 0
    for row in pending:
        key = f"r{row['RID']}"
        url = file_url(row)
        name = f"{key}__{safe_token(row['SFName'])}"
        print(f"[{key}] {row['DeviceType']} {row['BVersion']} ({row['APPName']}) -> {url}")
        entry = index.setdefault(key, {})
        entry.update({k: row[k] for k in ("DeviceType", "APPName", "DeviceCategory", "Solution")})
        if args.dry_run:
            done += 1
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                path = Path(td) / name
                md5, sha, size = download(url, path)
                if md5 != row["FMD5"].strip().lower() or size != int(row["file_size"]):
                    raise RuntimeError(f"md5 {md5} size {size}, the list says {row['FMD5']} {row['file_size']}")
                if sha in by_sha:
                    name = by_sha[sha]  # the same file for another row: one asset
                elif name in assets:
                    raise RuntimeError(f"{name} is on the release with a different file")
                else:
                    gh("release", "upload", RELEASE_TAG, str(path))
                    assets[name], by_sha[sha] = sha, name
        except Unavailable as e:
            print(f"  {e}; recorded as unavailable")
            entry.setdefault("unavailable", []).append({"version": row["BVersion"], "md5": row["FMD5"].strip().lower(),
                                                       "url": url, "checked_at": now()})
            gone += 1
            save_index(index)
            continue
        except Exception as e:
            failures += 1
            print(f"  FAILED: {e!r}", file=sys.stderr)
            continue
        entry.setdefault("revisions", []).append({
            "version": row["BVersion"], "release_date": row["ReleaseDate"], "file": row["SFName"],
            "md5": md5, "sha256": sha, "size": size, "source_url": url,
            "asset_url": f"https://github.com/{slug}/releases/download/{RELEASE_TAG}/{name}",
            "archived_at": now()})
        save_index(index)
        done += 1
        since += 1
        if since >= args.commit_every:
            commit_and_push(since)
            since = 0
    if since and not args.dry_run:
        commit_and_push(since)
    print(f"\nDone. archived={done} unavailable={gone} failures={failures}")
    return 1 if done == 0 and gone == 0 and failures else 0


if __name__ == "__main__":
    sys.exit(main())
