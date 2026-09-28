#!/data/data/com.termux/files/usr/bin/python3
import argparse, hashlib, json, os, re, shutil, subprocess, time, urllib.request, zipfile
from pathlib import Path

MIRROR = "https://kmpdlizvwzdxplbarhcv.supabase.co/functions/v1/github-asset-mirror"
LOCAL_ROOT = Path("/sdcard/Pictures/G-ShaNiu/Publish")
MAX_BUNDLE_BYTES = 25 * 1024 * 1024\nMANAGED_DIR = re.compile(r"^hundred-cities-\\d{3}$")

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def fetch(url: str, max_bytes: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "G-ShaNiu-AssetSync/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read(max_bytes + 1)
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

def sync(series: str, episode: str, cleanup_days: int):
    series = series.strip().lower()
    episode = episode.strip()
    if not series.replace("-", "").isalnum() or not episode.isdigit():
        raise RuntimeError("invalid_series_or_episode")

    base = f"{MIRROR}?series={series}&episode={episode}&file="
    manifest_bytes = fetch(base + "manifest.json", 512 * 1024)
    manifest = json.loads(manifest_bytes)
    if str(manifest.get("series")) != series or str(manifest.get("episode")) != episode:
        raise RuntimeError("manifest_identity_mismatch")

    bundle_meta = manifest.get("bundle") or {}
    bundle_name = str(bundle_meta.get("filename") or "bundle.zip")
    if bundle_name != Path(bundle_name).name or not bundle_name.endswith(".zip"):
        raise RuntimeError("invalid_bundle_name")

    if bundle_name != "bundle.zip":
        raise RuntimeError("bundle_name_must_be_bundle_zip")
    bundle = fetch(base + "bundle.zip", MAX_BUNDLE_BYTES)
    expected_bundle_sha = str(bundle_meta.get("sha256") or "").lower()
    if len(expected_bundle_sha) != 64 or sha256_bytes(bundle) != expected_bundle_sha:
        raise RuntimeError("bundle_sha_mismatch")
    expected_bundle_size = int(bundle_meta.get("size_bytes") or -1)
    if expected_bundle_size != len(bundle):
        raise RuntimeError("bundle_size_mismatch")

    target = LOCAL_ROOT / f"{series}-{episode}"
    temp = LOCAL_ROOT / f".{series}-{episode}.part"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True, exist_ok=True)

    expected_assets = manifest.get("assets") or []
    with zipfile.ZipFile(Path("/dev/stdin") if False else __import__("io").BytesIO(bundle)) as z:
        names = set(z.namelist())
        if "manifest.json" not in names:
            raise RuntimeError("bundle_manifest_missing")
        for i, asset in enumerate(expected_assets):
            if int(asset.get("ordinal", -1)) != i:
                raise RuntimeError("asset_ordinal_invalid")
            name = str(asset.get("filename") or "")
            if not safe_member(name) or name not in names:
                raise RuntimeError("asset_missing")
            data = z.read(name)
            if len(data) != int(asset.get("size_bytes") or -1):
                raise RuntimeError("asset_size_mismatch")
            if sha256_bytes(data) != str(asset.get("sha256") or "").lower():
                raise RuntimeError("asset_sha_mismatch")
            out = temp / f"{i+1:02d}{Path(name).suffix.lower() or '.jpg'}"
            out.write_bytes(data)

    (temp / "manifest.json").write_bytes(manifest_bytes)
    if target.exists():
        shutil.rmtree(target)
    temp.replace(target)
    now = time.time()
    os.utime(target, (now, now))

    scan_errors = []
    for p in sorted(target.iterdir()):
        if p.is_file() and p.name != "manifest.json":
            try:
                cp = subprocess.run(["termux-media-scan", str(p)], capture_output=True, text=True, timeout=20)
                if cp.returncode != 0:
                    scan_errors.append(p.name)
            except Exception:
                scan_errors.append(p.name)

    removed = clean_local(cleanup_days, keep=target)
    return {
        "status": "asset_sync_verified",
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
    ap.add_argument("--cleanup-days", type=int, default=7)
    args = ap.parse_args()
    print(json.dumps(sync(args.series, args.episode, args.cleanup_days), ensure_ascii=False))

if __name__ == "__main__":
    main()
