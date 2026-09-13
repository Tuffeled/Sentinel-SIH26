"""Generate a SYNTHETIC passport / ID dataset for the SENTINEL demo.

Produces paired GENUINE / ALTERED documents with:
  * a proper ICAO 9303 MRZ (valid check digits for genuine, corrupted for altered)
  * labelled visual-inspection-zone fields (that match the MRZ for genuine)
  * a procedurally-drawn face in the photo box
  * deliberate, detectable tampering in the altered variants:
        - MRZ checksum corruption
        - a visual-zone field changed to disagree with the MRZ
        - a locally re-compressed (spliced) region -> forensic ELA signal
        - (some) a swapped face photo

Everything is fictional. A ground-truth manifest.json is written for evaluation.

Run:  python backend/generate_synthetic_docs.py
"""
from __future__ import annotations

import io
import json
import random
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.config import settings  # noqa: E402
from app.services.mrz_service import check_digit  # noqa: E402

OUT = settings.synthetic_dir
OUT.mkdir(parents=True, exist_ok=True)

# --- Palette (document look) ---
PAPER = (238, 233, 222)
PAPER2 = (228, 221, 205)
INK = (26, 32, 44)
LABEL = (90, 96, 110)
ACCENT = (40, 70, 120)

WATCHLIST_NUMBER = "SP0000099"  # matched by the seeded synthetic watchlist


def _font(names, size):
    for name in names:
        for base in (r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu", ""):
            try:
                return ImageFont.truetype(str(Path(base) / name) if base else name, size)
            except Exception:
                continue
    return ImageFont.load_default()


F_TITLE = _font(["arialbd.ttf", "DejaVuSans-Bold.ttf"], 34)
F_LABEL = _font(["arial.ttf", "DejaVuSans.ttf"], 15)
F_VALUE = _font(["arialbd.ttf", "DejaVuSans-Bold.ttf"], 21)
F_SMALL = _font(["arial.ttf", "DejaVuSans.ttf"], 13)
# Lucida Console / Courier-Bold OCR far more reliably than Consolas for the MRZ.
F_MRZ = _font(["lucon.ttf", "courbd.ttf", "cour.ttf", "DejaVuSansMono.ttf"], 27)
F_WM = _font(["arialbd.ttf", "DejaVuSans-Bold.ttf"], 22)


# ---------------------------------------------------------------------------
# Procedural face
# ---------------------------------------------------------------------------
def draw_face(w: int, h: int, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (205, 214, 224))
    d = ImageDraw.Draw(img)
    # background gradient
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(200 - 20 * t), int(210 - 20 * t), int(224 - 15 * t)))

    skin = rnd.choice([(236, 200, 170), (222, 180, 150), (200, 158, 128),
                       (172, 128, 100), (240, 210, 185)])
    cx, cy = w // 2, int(h * 0.55)
    fw, fh = int(w * 0.52), int(h * 0.62)

    # hair (behind head)
    hair = rnd.choice([(40, 32, 28), (70, 50, 35), (25, 25, 30), (90, 70, 55)])
    d.ellipse([cx - fw // 2 - 8, cy - fh // 2 - 26, cx + fw // 2 + 8, cy + 6], fill=hair)
    # neck
    d.rectangle([cx - fw // 6, cy + fh // 4, cx + fw // 6, cy + fh // 2 + 30], fill=skin)
    # face oval
    d.ellipse([cx - fw // 2, cy - fh // 2, cx + fw // 2, cy + fh // 2], fill=skin)

    # shading (right side darker)
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.ellipse([cx, cy - fh // 2, cx + fw // 2, cy + fh // 2], fill=(0, 0, 0, 40))
    img = Image.alpha_composite(img.convert("RGBA"), shade).convert("RGB")
    d = ImageDraw.Draw(img)

    ew = fw // 6
    ey = cy - fh // 12
    for sx in (cx - fw // 5, cx + fw // 5):
        d.ellipse([sx - ew, ey - ew // 2, sx + ew, ey + ew // 2], fill=(250, 250, 250))
        d.ellipse([sx - ew // 3, ey - ew // 3, sx + ew // 3, ey + ew // 3],
                  fill=rnd.choice([(60, 40, 30), (40, 60, 90), (50, 90, 60)]))
        d.arc([sx - ew - 3, ey - ew, sx + ew + 3, ey + ew // 2], 200, 340, fill=(70, 55, 45), width=3)
    # nose
    d.line([(cx, ey + 6), (cx - 6, cy + fh // 10)], fill=(150, 110, 90), width=3)
    d.line([(cx - 6, cy + fh // 10), (cx + 8, cy + fh // 10)], fill=(150, 110, 90), width=3)
    # mouth
    my = cy + fh // 5
    d.arc([cx - fw // 6, my - 8, cx + fw // 6, my + 12], 10, 170, fill=(150, 80, 80), width=4)

    return img.filter(ImageFilter.GaussianBlur(0.6))


FACES_DIR = settings.gan_faces_dir


def _load_face(filename, w: int, h: int, seed: int) -> Image.Image:
    """Load a GAN-synthesised face and portrait-crop it to the photo box.

    Falls back to a procedurally-drawn face if the GAN image is unavailable.
    """
    if filename:
        path = FACES_DIR / filename
        if path.exists():
            src = Image.open(path).convert("RGB")
            sw, sh = src.size
            target = w / h
            crop_w = min(sw, int(sh * target))
            crop_h = min(sh, int(crop_w / target))
            x0 = (sw - crop_w) // 2
            y0 = max(0, int(sh * 0.04))
            y0 = min(y0, sh - crop_h)
            src = src.crop((x0, y0, x0 + crop_w, y0 + crop_h))
            return src.resize((w, h), Image.LANCZOS)
    return draw_face(w, h, seed)


# ---------------------------------------------------------------------------
# MRZ
# ---------------------------------------------------------------------------
def _yymmdd(iso: str) -> str:
    dt = datetime.strptime(iso, "%Y-%m-%d")
    return dt.strftime("%y%m%d")


def build_td3(idn: dict, corrupt: str | None = None) -> list[str]:
    country = idn["nat"]
    surname = idn["surname"].replace(" ", "<")
    given = idn["given"].replace(" ", "<")
    name = f"{surname}<<{given}"
    line1 = ("P<" + country + name).ljust(44, "<")[:44]

    num = idn["num"].ljust(9, "<")[:9]
    num_cd = str(check_digit(num))
    dob = _yymmdd(idn["dob"])
    dob_cd = str(check_digit(dob))
    exp = _yymmdd(idn["expiry"])
    exp_cd = str(check_digit(exp))
    personal = "".ljust(14, "<")
    personal_cd = str(check_digit(personal))

    if corrupt == "dob":
        dob_cd = str((int(dob_cd) + 3) % 10)
    elif corrupt == "number":
        num_cd = str((int(num_cd) + 4) % 10)
    elif corrupt == "expiry":
        exp_cd = str((int(exp_cd) + 5) % 10)

    composite_src = num + num_cd + dob + dob_cd + exp + exp_cd + personal + personal_cd
    comp_cd = str(check_digit(composite_src))
    if corrupt == "composite":
        comp_cd = str((int(comp_cd) + 2) % 10)

    line2 = (num + num_cd + country + dob + dob_cd + idn["sex"] + exp + exp_cd +
             personal + personal_cd + comp_cd).ljust(44, "<")[:44]
    return [line1, line2]


# ---------------------------------------------------------------------------
# Passport rendering
# ---------------------------------------------------------------------------
def render_passport(idn: dict, altered: bool = False) -> Image.Image:
    W, H = 1000, 660
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    # subtle non-repeating vertical gradient (avoids repetitive forensic artefacts)
    for y in range(H):
        t = y / H
        shade = (int(PAPER[0] - 10 * t), int(PAPER[1] - 10 * t), int(PAPER[2] - 12 * t))
        d.line([(0, y), (W, y)], fill=shade)

    d.rectangle([0, 0, W, 70], fill=ACCENT)
    d.text((24, 16), "PASSPORT", font=F_TITLE, fill=(240, 240, 245))
    d.text((300, 26), "REPUBLIC OF UTOPIA  ·  SYNTHETIC SPECIMEN", font=F_LABEL,
           fill=(220, 226, 236))

    # photo box + face
    px, py, pw, ph = 34, 110, 250, 320
    d.rectangle([px, py, px + pw, py + ph], outline=INK, width=2)
    face_file = idn.get("alt_face") if (altered and idn.get("swap_face")) else idn.get("face")
    face = _load_face(face_file, pw - 8, ph - 8, idn["seed"] + (500 if altered and idn.get("swap_face") else 0))
    img.paste(face, (px + 4, py + 4))

    # VIZ fields (altered may change one to disagree with the MRZ)
    dob_display = idn["dob"]
    surname_display = idn["surname"]
    if altered and idn.get("alter_field") == "dob":
        dt = datetime.strptime(idn["dob"], "%Y-%m-%d")
        dob_display = dt.replace(year=dt.year - 6).strftime("%Y-%m-%d")
    if altered and idn.get("alter_field") == "name":
        surname_display = idn.get("alt_surname", "MARKHAM")

    def fmt_date(iso):
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d %b %Y").upper()

    fields = [
        ("Type / Code", f"P / {idn['nat']}"),
        ("Passport No.", idn["num"]),
        ("Surname", surname_display),
        ("Given Names", idn["given"]),
        ("Nationality", idn["nat"]),
        ("Date of Birth", fmt_date(dob_display)),
        ("Sex", idn["sex"]),
        ("Place of Birth", idn["pob"]),
        ("Date of Issue", fmt_date(idn["issue"])),
        ("Date of Expiry", fmt_date(idn["expiry"])),
    ]
    fx, fy = 320, 110
    col2 = 660
    for i, (label, value) in enumerate(fields):
        x = fx if i < 6 else col2
        y = fy + (i % 6) * 52 if i < 6 else fy + (i - 6) * 52
        d.text((x, y), label.upper(), font=F_LABEL, fill=LABEL)
        d.text((x, y + 18), value, font=F_VALUE, fill=INK)

    # MRZ band
    corrupt = idn.get("corrupt") if altered else None
    lines = build_td3(idn, corrupt=corrupt)
    my = H - 96
    d.rectangle([0, my - 12, W, H], fill=(246, 244, 238))
    d.line([(0, my - 12), (W, my - 12)], fill=INK, width=1)
    for i, line in enumerate(lines):
        d.text((24, my + i * 40), line, font=F_MRZ, fill=INK)

    # watermark
    d.text((px + 6, py + ph - 30), "SYNTHETIC", font=F_WM, fill=(200, 60, 60))

    if altered:
        img = _splice_region(img, box=(fx - 6, fy + 5 * 52, fx + 300, fy + 6 * 52 + 8))
    return img


def _splice_region(img: Image.Image, box) -> Image.Image:
    """Re-compress a rectangular region at low quality and paste it back,
    introducing a localised compression anomaly (detectable by ELA)."""
    region = img.crop(box)
    buf = io.BytesIO()
    region.save(buf, "JPEG", quality=45)
    buf.seek(0)
    degraded = Image.open(buf).convert("RGB")
    img.paste(degraded, (box[0], box[1]))
    return img


# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------
IDENTITIES = [
    {"id": "001", "surname": "HARGREAVE", "given": "JONATHAN MICHAEL", "sex": "M",
     "nat": "UTO", "dob": "1990-04-12", "issue": "2019-06-01", "expiry": "2029-05-31",
     "pob": "CENTRALIA", "num": "SP0000001", "seed": 11,
     "face": "gan_01.jpg", "corrupt": "dob", "alter_field": "dob"},
    {"id": "002", "surname": "VOSKUIJLEN", "given": "ELENA MARIA", "sex": "F",
     "nat": "UTO", "dob": "1985-11-23", "issue": "2020-02-15", "expiry": "2030-02-14",
     "pob": "PORT ARENDA", "num": "SP0000002", "seed": 22,
     "face": "gan_02.jpg", "alt_face": "gan_05.jpg",
     "corrupt": "composite", "alter_field": "dob", "swap_face": True},
    {"id": "003", "surname": "OKONKWO", "given": "DANIEL CHUKA", "sex": "M",
     "nat": "UTO", "dob": "1993-07-05", "issue": "2021-09-10", "expiry": "2031-09-09",
     "pob": "NEW HAVEN", "num": "SP0000003", "seed": 33,
     "face": "gan_03.jpg", "corrupt": "number", "alter_field": "dob"},
    {"id": "004", "surname": "TANAKA", "given": "YUKI", "sex": "F",
     "nat": "UTO", "dob": "1998-01-30", "issue": "2022-03-20", "expiry": "2032-03-19",
     "pob": "EASTMARCH", "num": "SP0000004", "seed": 44,
     "face": "gan_04.jpg", "alt_face": "gan_06.jpg",
     "corrupt": "expiry", "alter_field": "dob", "swap_face": True},
    {"id": "005", "surname": "ABRANTES", "given": "SOFIA LUISA", "sex": "F",
     "nat": "UTO", "dob": "1979-09-17", "issue": "2018-12-01", "expiry": "2028-11-30",
     "pob": "SOUTHRIDGE", "num": "SP0000005", "seed": 55,
     "face": "gan_07.jpg", "corrupt": "dob", "alter_field": "dob"},
]

# A clean, genuine-looking passport whose number is on the synthetic watchlist
# (for the watchlist demo; kept OUT of the genuine/altered evaluation pairs).
WATCHLIST_IDENTITY = {
    "id": "099", "surname": "MERCER", "given": "ADRIAN COLE", "sex": "M",
    "nat": "UTO", "dob": "1988-03-08", "issue": "2020-07-01", "expiry": "2030-06-30",
    "pob": "CENTRALIA", "num": WATCHLIST_NUMBER, "seed": 99, "face": "gan_08.jpg",
}


def main() -> None:
    # Remove any documents from a previous run so the folder stays clean.
    for old in list(OUT.glob("passport_*.png")) + list(OUT.glob("passport_*.jpg")):
        old.unlink()

    manifest = {"generated_at": datetime.utcnow().isoformat() + "Z",
                "notice": "SYNTHETIC DATA ONLY — fictional documents for demonstration.",
                "documents": [], "extra_documents": []}

    for idn in IDENTITIES:
        for altered in (False, True):
            img = render_passport(idn, altered=altered)
            suffix = "altered" if altered else "genuine"
            name = f"passport_{idn['id']}_{suffix}.jpg"
            img.save(OUT / name, "JPEG", quality=92)
            manifest["documents"].append({
                "file": name, "ground_truth": "ALTERED" if altered else "GENUINE",
                "identity": idn["id"], "type": "PASSPORT"})
            print(f"  wrote {name}")

    # Watchlist demo document (not part of eval pairs)
    wl_img = render_passport(WATCHLIST_IDENTITY, altered=False)
    wl_name = f"passport_{WATCHLIST_IDENTITY['id']}_watchlist_demo.jpg"
    wl_img.save(OUT / wl_name, "JPEG", quality=92)
    manifest["extra_documents"].append({
        "file": wl_name, "ground_truth": "GENUINE", "identity": "099",
        "type": "PASSPORT", "note": "identifier present in synthetic watchlist"})
    print(f"  wrote {wl_name}")

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDataset written to {OUT}")
    print(f"  {len(manifest['documents'])} evaluation documents "
          f"({sum(1 for d in manifest['documents'] if d['ground_truth']=='GENUINE')} genuine / "
          f"{sum(1 for d in manifest['documents'] if d['ground_truth']=='ALTERED')} altered)")
    print(f"  watchlist demo number: {WATCHLIST_NUMBER}")


if __name__ == "__main__":
    main()
