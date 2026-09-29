# G-ShaNiu Assets

Public distribution repository for **final Xiaohongshu publishing assets only**. It is a transport/archive surface, not a general-purpose file-transfer bucket.

## Canonical layout

New production packages use:

```text
hundred-cities/<episode>/
  manifest.json
  bundle.zip.b64
```

`manifest.json` is the source of truth for episode identity, asset order, byte size and SHA-256. The transport bundle is immutable per publish attempt and must be fetched from a **full 40-character Git commit**, not from a moving `main` URL.

The current production path is:

```text
G final assets
  -> Tinkle17/g-shaniu-assets
  -> jsDelivr @ full commit
  -> asset-bridge validation
  -> XHS formal publish pipeline
  -> MI6 staging
```

The device verifies the manifest, decoded bundle size/SHA-256 and every contained asset before UI work begins.

## Compatibility paths

Older material-transfer experiments created files such as:

```text
bundle.b64.000
bundle.b64.001
...
bundle.b64.json
```

and the legacy `github-asset-mirror` can reconstruct `bundle.zip` from them.

These files are **compatibility artifacts, not the canonical format**. They must not be removed merely because `bundle.zip.b64` exists. The mirror still had real 003/004 traffic on 2026-09-28, so chunk cleanup is deferred until the compatibility route has had a verified no-traffic retirement window or has first been upgraded and accepted against the canonical transport.

`scripts/asset_sync.py` and `infra/github-asset-mirror` are compatibility tooling. New production publishing should follow the canonical path above.

## Retention policy

Keep:
- current and recent final publish packages;
- manifests and immutable evidence needed to reproduce a publish;
- compatibility chunks while a live compatibility caller still exists.

Delete from current HEAD when no longer needed:
- handoff tests;
- transport experiments;
- duplicate temporary encodings;
- diagnostics and intermediate renders.

Git history remains the audit trail for removed repository files. Deleting a file from current HEAD does not rewrite history.

On MI6, final publish bytes are a cache/workspace rather than the authorization source. Local cleanup must be bounded, must never delete the currently active publish package, and must not touch unrelated photos or user media.

## Safety

- No credentials, tokens, login state, private data or unpublished sensitive material.
- No email or Google Drive production transport.
- No expiring ChatGPT attachment URL as a production source.
- No unpinned `main` URL for an authorized publish attempt.
- Temporary transfer directories such as `handoff-test/` are not durable assets and should be removed after their acceptance purpose is complete.
