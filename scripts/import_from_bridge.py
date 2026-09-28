#!/usr/bin/env python3
import argparse, hashlib, io, json, re, urllib.request, zipfile
from pathlib import Path

BRIDGE="https://kmpdlizvwzdxplbarhcv.supabase.co/functions/v1/asset-bridge"
ALLOWED_SERIES={"hundred-cities"}
UUID=re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
EP=re.compile(r"^[0-9]{3}$")

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--post-id",required=True)
    ap.add_argument("--series",required=True)
    ap.add_argument("--episode",required=True)
    args=ap.parse_args()
    if not UUID.match(args.post_id) or args.series not in ALLOWED_SERIES or not EP.match(args.episode):
        raise SystemExit("invalid_identity")

    req=urllib.request.Request(BRIDGE+"?post_id="+args.post_id,headers={"User-Agent":"G-ShaNiu-GitHub-Importer/1.0"})
    with urllib.request.urlopen(req,timeout=90) as r:
        source=r.read(25*1024*1024+1)
        header_sha=(r.headers.get("x-bundle-sha256") or "").lower()
    if len(source)>25*1024*1024 or sha(source)!=header_sha:
        raise SystemExit("source_bundle_integrity_failed")

    with zipfile.ZipFile(io.BytesIO(source)) as zin:
        m=json.loads(zin.read("manifest.json"))
        if m.get("post_id")!=args.post_id or m.get("content_gate")!="pass" or m.get("approval_state")!="approved":
            raise SystemExit("post_not_approved")
        if m.get("publish_authorized") is not True:
            raise SystemExit("publish_not_authorized")
        assets=m.get("assets") or []
        if not assets or len(assets)>18 or int(m.get("asset_count") or 0)!=len(assets):
            raise SystemExit("asset_count_invalid")

        public_assets=[]
        outbuf=io.BytesIO()
        with zipfile.ZipFile(outbuf,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as zout:
            for i,a in enumerate(assets):
                if int(a.get("ordinal",-1))!=i:
                    raise SystemExit("ordinal_invalid")
                src=str(a.get("bundle_path") or "")
                data=zin.read(src)
                if len(data)!=int(a.get("size_bytes") or -1) or sha(data)!=str(a.get("sha256") or "").lower():
                    raise SystemExit("asset_integrity_failed")
                ext=Path(str(a.get("filename") or "")).suffix.lower() or ".jpg"
                name=f"{i+1:02d}{ext}"
                zout.writestr(name,data)
                public_assets.append({
                    "ordinal":i,"filename":name,"size_bytes":len(data),"sha256":sha(data),
                    "source_filename":a.get("filename")
                })
            bundle_manifest={"schema":"g-shaniu-assets-v1","series":args.series,"episode":args.episode,
                             "post_id":args.post_id,"asset_count":len(public_assets),"assets":public_assets}
            zout.writestr("manifest.json",json.dumps(bundle_manifest,ensure_ascii=False,indent=2).encode())
        bundle=outbuf.getvalue()

    manifest={
        "schema":"g-shaniu-assets-v1",
        "series":args.series,
        "episode":args.episode,
        "post_id":args.post_id,
        "post_slug":m.get("post_slug"),
        "title":m.get("title"),
        "version":"1",
        "asset_count":len(public_assets),
        "assets":public_assets,
        "bundle":{"filename":"bundle.zip","size_bytes":len(bundle),"sha256":sha(bundle)}
    }
    dst=Path(args.series)/args.episode
    dst.mkdir(parents=True,exist_ok=True)
    (dst/"bundle.zip").write_bytes(bundle)
    (dst/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":"imported","path":str(dst),"asset_count":len(public_assets),
                      "bundle_sha256":manifest["bundle"]["sha256"]},ensure_ascii=False))

if __name__=="__main__":
    main()
