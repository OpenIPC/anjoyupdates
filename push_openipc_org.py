#!/usr/bin/env python3
"""Tell openipc.org what this mirror holds, after each weekly run.

openipc.org's board catalogue offers each Anjoy Vision module the firmware
builds made for it. It never polls GitHub: this job pushes the whole list
once per run, and the push replaces what the site had
(https://github.com/OpenIPC/website/blob/master/service/internal/vendorfw/PUSH.md).

Needs `permissions: id-token: write`: the site checks a GitHub Actions OIDC
token (audience https://openipc.org) from this repository's
weekly-update.yml on main. There is no secret.

  python push_openipc_org.py [--dry-run] [--url https://dev.openipc.org/api/v1/vendor-firmware]
"""

import argparse
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = "https://openipc.org/api/v1/vendor-firmware"
AUDIENCE = "https://openipc.org"
CATEGORIES = {"i": "camera", "w": "wifi", "4": "4g", "n": "nvr", "d": "dvr"}


def items(index):
    """Every archived build: the board and build it is for (DeviceType, as
    Anjoy names it), whose build it is (APPName: public, or a customer's
    tag), its version and date, and the archived file."""
    out = []
    for key, e in sorted(index.items()):
        for r in e.get("revisions", []):
            date = r.get("release_date") or ""
            it = {"key": f"{key}__{r['version']}", "device_type": e["DeviceType"].strip(), "app": e["APPName"].strip(),
                  "category": CATEGORIES.get(e.get("DeviceCategory", ""), "other"), "version": r["version"].strip(),
                  "build": r.get("file") or e["DeviceType"], "asset_url": r["asset_url"], "sha256": r["sha256"],
                  "size": r["size"]}
            if len(date) == 8 and date.isdigit():
                it["published_at"] = f"{date[:4]}-{date[4:6]}-{date[6:]}T00:00:00Z"
            out.append(it)
    return out


def oidc_token():
    url, bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not bearer:
        sys.exit("no OIDC token: the job needs `permissions: id-token: write`")
    req = urllib.request.Request(url + "&audience=" + AUDIENCE, headers={"Authorization": "Bearer " + bearer})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["value"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the push's size and stop")
    ap.add_argument("--url", default=URL)
    args = ap.parse_args()
    with open("archive/index.json") as f:
        body = {"schema": 1, "source": "anjoyupdates", "items": items(json.load(f))}
    data = gzip.compress(json.dumps(body).encode())
    print(f"{len(body['items'])} items, {len(data)} bytes gzipped")
    if args.dry_run:
        return
    token = oidc_token()
    for attempt in range(5):
        req = urllib.request.Request(args.url, data=data, method="POST", headers={
            "Authorization": "Bearer " + token, "Content-Type": "application/json", "Content-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                print(r.status, r.read().decode())
                return
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code < 500:
                sys.exit(f"refused: {e.code} {msg}")
            print(f"attempt {attempt + 1}: {e.code} {msg}")
        except urllib.error.URLError as e:
            print(f"attempt {attempt + 1}: {e.reason}")
        time.sleep(30 * (attempt + 1))
    sys.exit("openipc.org did not take the push")


if __name__ == "__main__":
    main()
