#!/usr/bin/env python3
import base64, hashlib, io, json, re, zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path("hundred-cities/004")
B64 = ROOT / "bundle.zip.b64"
OUT_MANIFEST = ROOT / "manifest.json"
FONT = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"

def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

raw = base64.b64decode(re.sub(rb"\\s+", b"", B64.read_bytes()))
with zipfile.ZipFile(io.BytesIO(raw), "r") as z:
    files = {name: z.read(name) for name in z.namelist()}

img = Image.open(io.BytesIO(files["01.jpg"])).convert("RGB")
draw = ImageDraw.Draw(img)
bg = img.getpixel((20, 20))
ink = (101, 85, 52)
# Replace only the old headline; preserve all other layout, route copy and series mark.
draw.rectangle((58, 98, 730, 286), fill=bg)
font = ImageFont.truetype(FONT, 120)
draw.text((74, 99), "松阳漫记", font=font, fill=ink)
cover = io.BytesIO()
img.save(cover, "JPEG", quality=93, subsampling=0, optimize=True, progressive=True)
files["01.jpg"] = cover.getvalue()

inside = json.loads(files["manifest.json"].decode("utf-8"))
inside["version"] = "v3.3-songyang-manji"
inside["source_version"] = "v3.3-songyang-manji"
inside["cover_headline"] = "松阳漫记"
for i, a in enumerate(inside["assets"]):
    name = a["filename"]
    b = files[name]
    a["ordinal"] = i
    a["size_bytes"] = len(b)
    a["sha256"] = sha256(b)
files["manifest.json"] = json.dumps(inside, ensure_ascii=False, indent=2).encode("utf-8")

out = io.BytesIO()
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for name in ["01.jpg","02.jpg","03.jpg","04.jpg","05.jpg","06.jpg","07.jpg","08.jpg","manifest.json"]:
        z.writestr(name, files[name])
bundle = out.getvalue()
B64.write_text(base64.b64encode(bundle).decode("ascii"), encoding="ascii")

outer = dict(inside)
outer["bundle"] = {
    "filename": "bundle.zip.b64",
    "size_bytes": len(bundle),
    "sha256": sha256(bundle),
    "encoding": "base64"
}
outer["built_by"] = "xhs004-songyang-manji-oneoff-v1"
OUT_MANIFEST.write_text(json.dumps(outer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(json.dumps({
    "cover_size": len(files["01.jpg"]),
    "cover_sha256": sha256(files["01.jpg"]),
    "bundle_size": len(bundle),
    "bundle_sha256": sha256(bundle),
}, ensure_ascii=False))
