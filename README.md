# anjoyupdates

A self-updating mirror of [Anjoy Vision](https://www.anjvision.com)'s camera-module firmware, kept for
[OpenIPC](https://openipc.org). Anjoy Vision (深圳市安佳威视) makes IP camera modules, 4G and Wi-Fi modules
and NVRs; its site's download centre links an upgrade server that lists every build it ships. This
repository copies that list and every build it names, so each one stays available with its checksum,
and tells openipc.org's board catalogue which builds exist for which module.

## Layout

| File | What it is |
|---|---|
| [`items.json`](items.json) | The upgrade server's list (`POST https://om.aiot99.com/api/FindFirmware`), sorted by `RID`. |
| [`archive/index.json`](archive/index.json) | `r<RID>` → the archived build: version, release date, file name, MD5, sha256, size and `asset_url` on this repo's `firmware-archive` release. |
| [`refresh.py`](refresh.py) | Refreshes `items.json`; all-or-nothing. |
| [`download_firmwares.py`](download_firmwares.py) | Downloads every row not archived yet from Anjoy's Aliyun OSS bucket, checks it against the list's MD5 and size, and uploads it as a release asset. |
| [`push_openipc_org.py`](push_openipc_org.py) | Pushes the archive's list to openipc.org over a GitHub OIDC token; no secret. |

## What a row is

`DeviceType` names the board and the build: `MCA31_V0_BU_LIGHT` is module MC-A31, hardware revision V0,
then the build's flavour (TF card, 4G, GB28181, RTMP, AF zoom...). `APPName` is `public` for Anjoy's own
builds, the ones its download page shows, or a customer's tag (`_WTD`, `_FN`...) for a build made for
one customer's app; both kinds are mirrored and the tag is kept.

Anjoy's own notes on its download page, for anyone flashing these:

- the 4G, Wi-Fi and NVR builds are its latest tested versions;
- for ordinary camera modules it publishes the bare module's firmware only: a finished camera's maker
  may ship a customised build (AF zoom, PTZ, GB28181), and a module build can remove those functions;
- upgrading long-used older modules carries a risk of bricking them.

## Automation

[`weekly-update.yml`](.github/workflows/weekly-update.yml) runs on Mondays and on demand: refresh the
list and commit it, archive new builds (`--max-per-run`, 100 by default), then push the list to
openipc.org from `main` (only while the repository variable `PUSH_OPENIPC_ORG` is `true`).
