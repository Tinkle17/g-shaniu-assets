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

MI6 never clones the full repository. ShaNiu/Hermes downloads only the requested manifest and bundle through the bounded `github-asset-mirror` relay, verifies the bundle SHA-256 and every contained asset, then atomically stages the episode under:

`/sdcard/Pictures/G-ShaNiu/Publish/<series>-<episode>/`

No GitHub credential is required because this repository contains only final assets intended for public posting. MI6 direct GitHub access is not relied on: both raw-file HTTPS and Git-over-HTTPS timed out in device acceptance on 2026-09-28.

## Retention

GitHub is the durable archive for final published assets. MI6 is a cache: each successful sync performs bounded lazy cleanup with a seven-day default retention, while never deleting the episode currently being synced. Cleanup is restricted in source to managed `hundred-cities-NNN` directories.

Intermediate renders, diagnostics, credentials, private data and unpublished sensitive material must never be committed here.
