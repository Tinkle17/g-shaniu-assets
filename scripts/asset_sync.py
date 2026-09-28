#!/data/data/com.termux/files/usr/bin/python3
import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

CDN_ROOT = "https://cdn.jsdelivr.net/gh/Tinkle17/g-shaniu-assets"
LOCAL_ROOT = Path("/sdcard/Pictures/G-ShaNiu/Publish")
MAX_MANIFEST_BYTES = 512 * 1024
MAX_TRANSPORT_BYTES = 40 * 1024 * 1024

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def fetch(url: str, max_bytes: int) -> bytes:
    cp = subprocess.run(
        [
            "curl", "-fL", "--retry", "2", "--retry-delay", "1",
            "--connect-timeout", "10", "--max-time", "90",
            "-A", "G-ShaNiu-AssetSync/2.0", url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=100,
    )
    if cp.returncode != 0:
        raise RuntimeError("download_failed:" + cp.stderr.decode("utf-8", "replace")[-240:])
    data = cp.stdout
    if len(data) > max_bytes:
        raise RuntimeError("download_too_large")
    return data

def safe_member(name: str) -> bool:
    p = Path(name)
    return bool(name) and not p.is_absolute() and ".." not in p.parts and p.name == name

def clean_local(days: int, keep: Path | None = None):
    if days < 1 or not LOCAL_ROOT.exists():
        return []
    cutoff = time.time() - days * 86400
    removed = []
    for p in LOCAL_ROOT.iterdir():
        if not p.is_dir() or (keep is not None and p == keep):
            continue
        try:
            if p.stat().st_mtime < cutoff:
                shutil.rmtree(p)
                removed.append(str(p))
        except FileNotFoundError:
            pass
    return removed

def decode_transport(payload: bytes, encoding: str) -> bytes:
    if encoding in ("", "binary", "raw"):
        return payload
    if encoding == "base64":
        try:
            return base64.b64decode(payload, validate=True)
        except Exception as e:
            raise RuntimeError("bundle_base64_invalid") from e
    raise RuntimeError("unsupported_bundle_encoding:" + encoding)

def sync(series: str, episode: str, ref: str, cleanup_days: int):
    series = series.strip().lower()
    episode = episode.strip()
    ref = ref.strip().lower()
    if not series.replace("-", "").isalnum() or not episode.isdigit():
        raise RuntimeError("invalid_series_or_episode")
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise RuntimeError("ref_must_be_full_commit_sha")

    base = f"{CDN_ROOT}@{ref}/{series}/{episode}"
    manifest_bytes = fetch(base + "/manifest.json", MAX_MANIFEST_BYTES)
    manifest = json.loads(manifest_bytes)
    if str(manifest.get("series")) != series or str(manifest.get("episode")) != episode:
        raise RuntimeError("manifest_identity_mismatch")

    bundle_meta = manifest.get("bundle") or {}
    bundle_name = str(bundle_meta.get("filename") or "")
    if bundle_name != Path(bundle_name).name or not bundle_name:
        raise RuntimeError("invalid_bundle_name")

    transport = fetch(base + "/" + bundle_name, MAX_TRANSPORT_BYTES)
    bundle = decode_transport(transport, str(bundle_meta.get("encoding") or "").lower())

    expected_bundle_sha = str(bundle_meta.get("sha256") or "").lower()
    if len(expected_bundle_sha) != 64 or sha256_bytes(bundle) != expected_bundle_sha:
        raise RuntimeError("bundle_sha_mismatch")
    if int(bundle_meta.get("size_bytes") or -1) != len(bundle):
        raise RuntimeError("bundle_size_mismatch")

    expected_assets = manifest.get("assets") or []
    if int(manifest.get("asset_count") or -1) != len(expected_assets) or not expected_assets:
        raise RuntimeError("asset_count_invalid")

    target = LOCAL_ROOT / f"{series}-{episode}"
    temp = LOCAL_ROOT / f".{series}-{episode}.part"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(bundle)) as z:
            names = set(z.namelist())
            if "manifest.json" not in names:
                raise RuntimeError("bundle_manifest_missing")
            inner = json.loads(z.read("manifest.json"))
            if str(inner.get("series")) != series or str(inner.get("episode")) != episode:
                raise RuntimeError("bundle_manifest_identity_mismatch")
            for i, asset in enumerate(expected_assets):
                if int(asset.get("ordinal", -1)) != i:
                    raise RuntimeError("asset_ordinal_invalid")
                name = str(asset.get("filename") or "")
                if not safe_member(name) or name not in names:
                    raise RuntimeError("asset_missing:" + name)
                data = z.read(name)
                if len(data) != int(asset.get("size_bytes") or -1):
                    raise RuntimeError("asset_size_mismatch:" + name)
                if sha256_bytes(data) != str(asset.get("sha256") or "").lower():
                    raise RuntimeError("asset_sha_mismatch:" + name)
                out = temp / f"{i+1:02d}{Path(name).suffix.lower() or '.jpg'}"
                out.write_bytes(data)

        (temp / "manifest.json").write_bytes(manifest_bytes)
        (temp / "source.json").write_text(
            json.dumps(
                {
                    "source": "jsdelivr-github",
                    "repository": "Tinkle17/g-shaniu-assets",
                    "commit": ref,
                    "bundle_sha256": expected_bundle_sha,
                    "synced_at_epoch": int(time.time()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if target.exists():
            shutil.rmtree(target)
        temp.replace(target)
    except Exception:
        if temp.exists():
            shutil.rmtree(temp)
        raise

    now = time.time()
    os.utime(target, (now, now))
    scan_errors = []
    for p in sorted(target.iterdir()):
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            try:
                cp = subprocess.run(["termux-media-scan", str(p)], capture_output=True, text=True, timeout=20)
                if cp.returncode != 0:
                    scan_errors.append(p.name)
            except Exception:
                scan_errors.append(p.name)

    removed = clean_local(cleanup_days, keep=target)
    return {
        "status": "asset_sync_verified",
        "source": "jsdelivr-github",
        "commit": ref,
        "series": series,
        "episode": episode,
        "asset_count": len(expected_assets),
        "bundle_sha256": expected_bundle_sha,
        "device_dir": str(target),
        "media_scan_errors": scan_errors,
        "local_cleanup_removed": removed,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("episode")
    ap.add_argument("--ref", required=True, help="full 40-character Git commit SHA")
    ap.add_argument("--cleanup-days", type=int, default=7)
    args = ap.parse_args()
    print(json.dumps(sync(args.series, args.episode, args.ref, args.cleanup_days), ensure_ascii=False))

if __name__ == "__main__":
    main()
