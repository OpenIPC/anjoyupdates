#!/usr/bin/env python3
"""Refresh items.json: every firmware build Anjoy Vision's upgrade server lists.

  python refresh.py

Anjoy Vision (anjvision.com, 深圳市安佳威视) publishes its camera modules'
firmware through the page its site's download centre links ("在线升级固件下载中心"),
https://om.aiot99.com/html/download.html, which reads the list from
POST https://om.aiot99.com/api/FindFirmware. Each row is one build:

  DeviceType   the board and build it is for: MCA31_V0_BU_LIGHT is MC-A31,
               hardware revision V0, a build flavour after it
  APPName      "public" for Anjoy's own builds (what the page shows), or a
               customer's tag (_WTD, _FN, ...) for a build made for one
  BVersion, ReleaseDate, FMD5, file_size, UpFile (the file on Anjoy's
  Aliyun OSS bucket), DeviceCategory (i camera module, w Wi-Fi, 4 4G,
  n NVR, d DVR)

The write is all-or-nothing: an error, an answer that is not a list, an empty
list, or one as long as the request's limit (it may have been cut short)
leaves items.json untouched and exits non-zero.
"""

import json
import os
import sys
import time

import requests

API = "https://om.aiot99.com/api/FindFirmware"
PAGE = "https://om.aiot99.com/html/download.html"
OUT = "items.json"
LIMIT = 5000
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/128.0 Safari/537.36", "Referer": PAGE}
REQUIRED = ("RID", "DeviceType", "APPName", "BVersion", "ReleaseDate", "UpFile", "SFName", "FMD5", "file_size")


def main():
    try:
        r = requests.post(API, json={"t": int(time.time()), "limit": LIMIT}, headers=HEADERS, timeout=120)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        sys.exit(f"refresh: {e}; {OUT} left as it was")
    if data.get("code") != 200 or data.get("msg") not in ("success", "OK"):
        sys.exit(f"refresh: the server answered {data.get('code')} {data.get('msg')!r}; {OUT} left as it was")
    rows = data.get("list")
    if not isinstance(rows, list) or not rows:
        sys.exit(f"refresh: no firmware listed; {OUT} left as it was")
    if len(rows) >= LIMIT:
        sys.exit(f"refresh: {len(rows)} rows, the request's limit: the list may be cut short; {OUT} left as it was")
    for row in rows:
        missing = [k for k in REQUIRED if row.get(k) in (None, "")]
        if missing:
            sys.exit(f"refresh: row {row.get('RID')} has no {', '.join(missing)}; {OUT} left as it was")
    rids = [row["RID"] for row in rows]
    if len(set(rids)) != len(rids):
        sys.exit(f"refresh: duplicate RIDs; {OUT} left as it was")
    rows.sort(key=lambda row: int(row["RID"]))
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"source": API, "rows": rows}, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    os.replace(tmp, OUT)
    print(f"refresh: {len(rows)} builds")


if __name__ == "__main__":
    main()
