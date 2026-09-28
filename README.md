# G-ShaNiu Assets

Public, read-only distribution repository for final publishing assets used by G-ShaNiu.

## Layout

```
hundred-cities/<episode>/
  manifest.json
  bundle.zip
scripts/
  asset_sync.py
```

Each `manifest.json` is the source of truth for asset count, SHA-256, original filenames, series episode and creation date.

## Device contract

MI6 never clones the full repository. ShaNiu/Hermes downloads only the requested manifest and bundle from `raw.githubusercontent.com`, verifies the bundle SHA-256 and every contained asset, then atomically stages the episode under:

`/sdcard/Pictures/G-ShaNiu/Publish/<series>-<episode>/`

No GitHub credential is required because this repository contains only final assets intended for public posting.

## Retention

GitHub is the durable archive for final published assets. MI6 is a cache: the sync script removes local publish directories older than 7 days by default, while never deleting the episode currently being synced.

Intermediate renders, diagnostics, credentials, private data and unpublished sensitive material must never be committed here.
