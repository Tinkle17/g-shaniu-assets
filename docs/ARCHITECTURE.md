# Asset transport architecture

## Production path

```
G / content pipeline
  -> Tinkle17/g-shaniu-assets (public final assets only)
  -> github-asset-mirror (bounded read-only mirror)
  -> ShaNiu / Hermes
  -> ~/.hermes/scripts/asset_sync.py
  -> /sdcard/Pictures/G-ShaNiu/Publish/hundred-cities-NNN/
  -> Android Media Scanner
  -> official Xiaohongshu publish flow
```

GitHub is the durable source of truth. The mirror exists only because MI6 direct access to both `raw.githubusercontent.com` and Git-over-HTTPS was observed timing out on 2026-09-28. It accepts only allowlisted series, a three-digit episode, and `manifest.json` or `bundle.zip`; it cannot proxy arbitrary URLs or paths.

The device validates the bundle SHA-256, byte length, per-image SHA-256 and ordinal order before atomically replacing the local episode directory. Local material is a cache. Cleanup is performed during subsequent syncs with a seven-day default retention.

## Bootstrap exception

Episodes 003 and 004 were seeded as bounded `bundle.b64.NNN` text parts because the chat GitHub connector could not atomically write the bootstrap binary blobs. `bundle.b64.json` declares the exact decoded size and SHA-256. Mirror v2 reconstructs and verifies those bundles. Normal future imports write a regular `bundle.zip`.

## Future imports

Create a JSON request under `requests/` with:

```json
{"post_id":"<approved content_posts UUID>","series":"hundred-cities","episode":"005"}
```

The GitHub workflow validates approval and hashes through the content asset bridge, creates the standardized bundle, commits it, and deletes the request. Never commit credentials, drafts containing private data, diagnostics, or non-final assets.
