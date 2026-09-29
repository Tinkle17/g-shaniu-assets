#!/usr/bin/env python3
import argparse, base64, hashlib, io, json, zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]

FONT_CANDIDATES=[
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
]

def sha(b:bytes)->str:
    return hashlib.sha256(b).hexdigest()

def load_font(size:int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p,size=size,index=2 if p.endswith(".ttc") else 0)
    raise SystemExit("cjk_font_missing")

def fit_font(draw,text,max_width,start=112,min_size=72):
    for size in range(start,min_size-1,-2):
        f=load_font(size)
        box=draw.textbbox((0,0),text,font=f)
        if box[2]-box[0] <= max_width:
            return f
    raise SystemExit("headline_too_wide")

def patch(series,episode,headline):
    if series!="hundred-cities" or not episode.isdigit() or len(episode)!=3:
        raise SystemExit("invalid_identity")
    dst=ROOT/series/episode
    manifest_path=dst/"manifest.json"
    b64_path=dst/"bundle.zip.b64"
    if not manifest_path.exists() or not b64_path.exists():
        raise SystemExit("bundle_missing")
    repo_manifest=json.loads(manifest_path.read_text())
    zip_bytes=base64.b64decode(b64_path.read_bytes())
    with zipfile.ZipFile(io.BytesIO(zip_bytes),"r") as zin:
        names=zin.namelist()
        files={n:zin.read(n) for n in names}
    if "01.jpg" not in files or "manifest.json" not in files:
        raise SystemExit("bundle_contract_invalid")

    im=Image.open(io.BytesIO(files["01.jpg"])).convert("RGB")
    if im.size!=(1080,1440):
        raise SystemExit("cover_geometry_drift")
    draw=ImageDraw.Draw(im)
    bg=im.getpixel((24,110))
    # Preserve the top rule and all lower layout. Replace only the old headline block.
    draw.rectangle((62,105,760,285),fill=bg)
    headline=str(headline).strip()
    font=fit_font(draw,headline,620)
    ink=(101,88,57)
    draw.text((76,122),headline,font=font,fill=ink,spacing=0)

    out=io.BytesIO()
    im.save(out,format="JPEG",quality=92,optimize=True,subsampling=1)
    cover=out.getvalue()
    files["01.jpg"]=cover

    inner=json.loads(files["manifest.json"])
    if isinstance(inner.get("assets"),list) and inner["assets"]:
        inner["assets"][0]["size_bytes"]=len(cover)
        inner["assets"][0]["sha256"]=sha(cover)
    inner["cover_headline"]=headline
    files["manifest.json"]=(json.dumps(inner,ensure_ascii=False,indent=2)+"\n").encode()

    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as zout:
        for n in names:
            zout.writestr(n,files[n])
    bundle=buf.getvalue()
    b64=base64.b64encode(bundle).decode("ascii")
    b64_path.write_text(b64)

    if isinstance(repo_manifest.get("assets"),list) and repo_manifest["assets"]:
        repo_manifest["assets"][0]["size_bytes"]=len(cover)
        repo_manifest["assets"][0]["sha256"]=sha(cover)
    repo_manifest["cover_headline"]=headline
    repo_manifest["version"]="v3.3-songyang-manji" if episode=="004" else str(repo_manifest.get("version") or "patched")
    repo_manifest["bundle"]={
        "filename":"bundle.zip.b64",
        "size_bytes":len(bundle),
        "sha256":sha(bundle),
        "encoding":"base64"
    }
    manifest_path.write_text(json.dumps(repo_manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({
        "status":"cover_patched","series":series,"episode":episode,"headline":headline,
        "cover_sha256":sha(cover),"cover_size":len(cover),
        "bundle_sha256":sha(bundle),"bundle_size":len(bundle)
    },ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--series",required=True)
    ap.add_argument("--episode",required=True)
    ap.add_argument("--headline",required=True)
    a=ap.parse_args()
    patch(a.series,a.episode,a.headline)

if __name__=="__main__":
    main()
