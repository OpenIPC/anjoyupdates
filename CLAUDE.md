# CLAUDE.md

A mirror of Anjoy Vision's firmware builds for OpenIPC: data (`items.json`, `archive/index.json`) and three
scripts run by `.github/workflows/weekly-update.yml`. Most commits are made by `anjoyupdates-bot`.

- `python refresh.py` — rewrite `items.json` from `POST https://om.aiot99.com/api/FindFirmware`
  (`{"t": <unix time>, "limit": 5000}`); all-or-nothing, refuses a list as long as the limit.
- `GH_TOKEN=$(gh auth token) python download_firmwares.py --dry-run` — the plan; without `--dry-run` it
  uploads to the real `firmware-archive` release and commits and pushes `archive/index.json` itself.
- `python push_openipc_org.py --dry-run` — the push's size. The real push needs the workflow's OIDC token;
  openipc.org accepts it only from `weekly-update.yml` on `main` (the contract is
  `service/internal/vendorfw/PUSH.md` in OpenIPC/website, source `anjoyupdates`).

Gotchas:

- Files live at `https://ossfiles002.oss-cn-shanghai.aliyuncs.com/<UpFile>` (what the vendor's download
  page links). A download is kept only when its MD5 and size equal the list's; a mismatch is retried next
  run, a 403/404/410 recorded under `unavailable`.
- 80 rows share a file with another row: one asset, found by sha256, serves all of them.
- `APPName` other than `public` marks a customer's build; keep it, the site labels it.
- Asset names are `r<RID>__<file name>` with only `[A-Za-z0-9._-]` (GitHub renames others silently).
