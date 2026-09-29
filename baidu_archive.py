#!/usr/bin/env python3
"""Archive Anjoy's collection of firmware for its pre-2022 modules.

  GH_TOKEN=... python baidu_archive.py <folder> [--dry-run]

Anjoy's download centre keeps the firmware for its older modules (MC200E,
MC500L, MT200E5 and about thirty more) not on its upgrade server but in a
Baidu Pan share: https://pan.baidu.com/s/1QzNFsECtzzJ7rr3_QwEGgQ (extraction
code 1234), folder 旧型号升级固件合集 ("upgrade firmware for old models"),
laid out as <module>/[<variant>/]firmware_<build>_V<x.y.z.w>_..._<yyyymmdd...>.bin.
Baidu serves the files to a signed-in account only, so this is run by hand on
a copy of the folder (downloaded 2026-09-29; 108 files, sizes as Baidu lists
them) rather than by the weekly job.

Each file becomes a release asset b__<module>__<sha8>__<file name> (uploaded
once, found by sha256) and an index entry b<sha256[:12]> marked
"Collection": "pre-2022", with the module and variant the folders give -- the
variant (暖光（软光敏）_自动聚焦: warm light, software light sensing, autofocus)
in Chinese as the folder names it and in English and Russian. Running it again
adds nothing.
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import download_firmwares as d

SHARE = "https://pan.baidu.com/s/1QzNFsECtzzJ7rr3_QwEGgQ"
# firmware_MT200E5_V0_AF-GLK_V3.0.2.3_TF_MT200E5_LIGHT_V0_202008041015.bin
NAME = re.compile(r"^firmware_(?P<build>.+?)_V(?P<version>\d+(?:\.\d+){2,3})(?:_.*)?_(?P<date>20\d{6})\d*\.bin$", re.I)
# The variant folders' words, as Anjoy writes them.
WORDS = {
    "普通红外": ("standard IR", "обычная ИК-подсветка"),
    "软光敏红外": ("IR with software light sensing", "ИК-подсветка с программным датчиком освещённости"),
    "暖光（软光敏）": ("warm light (software light sensing)", "тёплый свет (программный датчик освещённости)"),
    "暖光（软光敏)": ("warm light (software light sensing)", "тёплый свет (программный датчик освещённости)"),
    "暖光": ("warm light", "тёплый свет"),
    "红外": ("IR", "ИК-подсветка"),
    "双光源": ("dual light", "двойная подсветка"),
    "自动聚焦": ("autofocus", "автофокус"),
    "枪机": ("bullet camera", "цилиндрическая камера"),
    "球机": ("dome camera", "купольная камера"),
    "双光源枪机": ("dual light, bullet camera", "двойная подсветка, цилиндрическая камера"),
    "双光源球机": ("dual light, dome camera", "двойная подсветка, купольная камера"),
    "暖光球机": ("warm light, dome camera", "тёплый свет, купольная камера"),
    "MCJ10蓝色WEB不带人形": ("MCJ10, blue web interface, without human detection",
                           "MCJ10, синий веб-интерфейс, без детекции людей"),
}


def variant(label):
    """{zh, en, ru} for a variant folder: its words joined; None when a word
    is not known (the script stops rather than guess)."""
    if not label:
        return None
    if label in WORDS:
        en, ru = WORDS[label]
        return {"zh": label, "en": en, "ru": ru}
    parts = [WORDS.get(p) for p in label.split("_")]
    if not all(parts):
        sys.exit(f"variant {label!r}: a word WORDS does not translate")
    return {"zh": label, "en": ", ".join(p[0] for p in parts), "ru": ", ".join(p[1] for p in parts)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = Path(args.folder).expanduser()
    files = sorted(p for p in root.rglob("*.bin") if p.is_file())
    if not files:
        sys.exit(f"no .bin files under {root}")
    index = d.load_index()
    if not args.dry_run:
        d.ensure_release_exists()
    assets = d.existing_release_assets() if not args.dry_run else {}
    by_sha = {sha: name for name, sha in assets.items() if sha}
    slug = d.repo_slug()
    added = 0
    for path in files:
        rel = path.relative_to(root)
        module, sub = rel.parts[0], "_".join(rel.parts[1:-1])
        m = NAME.match(path.name)
        if not m:
            sys.exit(f"{rel}: the file name does not read as firmware_<build>_V<version>_..._<date>.bin")
        data = path.read_bytes()
        sha, md5 = hashlib.sha256(data).hexdigest(), hashlib.md5(data).hexdigest()
        key = f"b{sha[:12]}"
        if key in index:
            continue
        name = f"b__{d.safe_token(module)}__{sha[:8]}__{d.safe_token(path.name)}"
        print(f"[{key}] {module} / {sub or '-'} / {path.name}")
        if not args.dry_run:
            if sha in by_sha:
                name = by_sha[sha]
            elif name in assets:
                sys.exit(f"{name} is on the release with a different file")
            else:
                # gh names an asset after its file: upload a copy named so.
                with tempfile.TemporaryDirectory() as td:
                    copy = Path(td) / name
                    shutil.copyfile(path, copy)
                    d.gh("release", "upload", d.RELEASE_TAG, str(copy))
                assets[name], by_sha[sha] = sha, name
        index[key] = {
            "DeviceType": m.group("build"), "APPName": "public", "DeviceCategory": "i", "Solution": "",
            "Collection": "pre-2022", "Module": module, "Variant": variant(sub), "BaiduPath": str(rel),
            "revisions": [{"version": m.group("version"), "release_date": m.group("date"), "file": path.name,
                           "md5": md5, "sha256": sha, "size": len(data), "source_url": SHARE,
                           "asset_url": f"https://github.com/{slug}/releases/download/{d.RELEASE_TAG}/{name}",
                           "archived_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}],
        }
        added += 1
    if not args.dry_run and added:
        d.save_index(index)
    print(f"{added} added, {len(files)} files")


if __name__ == "__main__":
    main()
