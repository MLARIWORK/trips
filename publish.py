#!/usr/bin/env python3
"""
publish.py -- one-command publisher for the trips photo journal.

Usage:
    python publish.py                     Process photos, rebuild site, commit + push
    python publish.py --no-push           Same, but skip the git commit/push step
    python publish.py -m "message"        Use a custom commit message
    python publish.py new "Kyoto, Japan"  Create a new trip folder with a notes template

Workflow for a new trip:
    1. python publish.py new "Kyoto, Japan"      (or just create a folder under trips/)
    2. Copy your photos into the new folder (originals are kept untouched).
    3. Edit notes.md in that folder: dates, notes, memories, photo captions.
    4. python publish.py
"""

import argparse
import json
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRIPS_DIR = ROOT / "trips"
MEDIA_DIR = ROOT / "media"
MANIFEST = ROOT / "manifest.json"
SITE_CONFIG = ROOT / "site.json"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp",
              ".tif", ".tiff", ".bmp", ".gif"}
THUMB_MAX = 800     # max dimension (px) for grid thumbnails
WEB_MAX = 2000      # max dimension (px) for lightbox viewing copies
THUMB_QUALITY = 80
WEB_QUALITY = 87

EXIF_DATETIME_ORIGINAL = 36867
EXIF_ORIENTATION = 274

try:
    from PIL import Image, ImageOps
except ImportError:
    print("Pillow is required. Install dependencies with:")
    print("    python -m pip install -r requirements.txt")
    sys.exit(1)

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_OK = True
except ImportError:
    HEIC_OK = False


# ---------------------------------------------------------------- helpers

def slugify(text):
    text = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower())
    return text.strip("-") or "trip"


def media_name(filename, kind):
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", filename)
    return f"{safe}__{kind}.jpg"


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


def run_git(args, capture=False):
    result = subprocess.run(["git"] + args, cwd=ROOT,
                            capture_output=capture, text=True)
    return result


# ---------------------------------------------------------------- notes.md

NOTES_TEMPLATE = """---
title: {title}
location:
dates:
date: {date}
cover:
---

Write your notes, memories, and stories here. Markdown works:
**bold**, *italic*, lists, headings, [links](https://example.com).

## Photo captions

<!-- One line per photo, "filename: caption". Delete lines you don't need. -->
"""


def extract_section(body, title):
    """Pull a '## <title>' section out of the notes body.

    Returns (section_text, body_without_section). The section runs until
    the next heading or end of file.
    """
    m = re.search(rf"^##\s*{title}\s*$", body, re.IGNORECASE | re.MULTILINE)
    if not m:
        return "", body
    rest = body[m.end():]
    nxt = re.search(r"^#{1,6}\s", rest, re.MULTILINE)
    if nxt:
        return rest[:nxt.start()], body[:m.start()] + rest[nxt.start():]
    return rest, body[:m.start()]


def section_lines(text):
    for line in text.splitlines():
        line = re.sub(r"<!--.*?-->", "", line).strip()
        yield re.sub(r"^[-*]\s+", "", line)


def parse_notes(path):
    """Parse a notes.md file.

    Returns (meta dict, notes markdown, captions dict,
    place display names dict, place order list).
    """
    meta, body = {}, ""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\s*---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition(":")
                meta[key.strip().lower()] = value.strip()
        body = text[m.end():]
    else:
        body = text

    # "## Photo captions" and "## Places" are data sections, not visible notes.
    captions = {}
    cap_text, body = extract_section(body, "photo captions")
    for line in section_lines(cap_text):
        cm = re.match(r"(.+?\.[A-Za-z0-9]{2,5})\s*:\s*(.+)$", line)
        if cm:
            captions[cm.group(1).strip().lower().replace("\\", "/")] = \
                cm.group(2).strip()

    place_names, place_order = {}, []
    places_text, body = extract_section(body, "places")
    for line in section_lines(places_text):
        pm = re.match(r"(.+?)\s*:\s*(.+)$", line)
        if pm:
            folder = pm.group(1).strip().lower()
            place_names[folder] = pm.group(2).strip()
            place_order.append(folder)

    return meta, body.strip(), captions, place_names, place_order


# ---------------------------------------------------------------- photos

def read_photo_info(src):
    """Open the image lazily and return (width, height, taken, needs_heic_warn)."""
    with Image.open(src) as im:
        width, height = im.size
        taken = None
        orientation = None
        try:
            exif = im.getexif()
            raw = exif.get(EXIF_DATETIME_ORIGINAL)
            if not raw:
                raw = exif.get_ifd(0x8769).get(EXIF_DATETIME_ORIGINAL)
            if raw:
                taken = datetime.strptime(str(raw).strip(),
                                          "%Y:%m:%d %H:%M:%S")
            orientation = exif.get(EXIF_ORIENTATION)
        except Exception:
            pass
        if orientation in (5, 6, 7, 8):
            width, height = height, width
    return width, height, taken


def generate_derivative(src, dest, max_dim, quality):
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", im.size, (255, 255, 255))
            im = im.convert("RGBA")
            background.paste(im, mask=im.split()[-1])
            im = background
        elif im.mode != "RGB":
            im = im.convert("RGB")
        im.thumbnail((max_dim, max_dim), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "JPEG", quality=quality, optimize=True,
                progressive=True)


def process_trip(trip_dir):
    """Process one trip folder; returns the manifest entry."""
    slug = trip_dir.name
    # Photos directly in the trip folder are ungrouped; photos in a
    # subfolder belong to that "place" (a stop within the trip).
    photo_sources = []
    for entry in sorted(trip_dir.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_file() and entry.suffix.lower() in IMAGE_EXTS:
            photo_sources.append((entry, ""))
        elif entry.is_dir() and not entry.name.startswith("."):
            for sub in sorted(entry.iterdir(), key=lambda p: p.name.lower()):
                if sub.is_file() and sub.suffix.lower() in IMAGE_EXTS:
                    photo_sources.append((sub, entry.name))
    if not photo_sources:
        return None

    notes_path = trip_dir / "notes.md"
    if not notes_path.exists():
        title = re.sub(r"^\d{4}-\d{2}(-\d{2})?-?", "", slug)
        title = title.replace("-", " ").strip().title() or slug
        notes_path.write_text(
            NOTES_TEMPLATE.format(title=title,
                                  date=datetime.now().strftime("%Y-%m-%d")),
            encoding="utf-8")
        print(f"  created notes template: trips/{slug}/notes.md")
    meta, notes_md, captions, place_names, place_order = parse_notes(notes_path)

    out_dir = MEDIA_DIR / slug
    expected_media = set()
    photos = []
    generated = 0

    for src, place in photo_sources:
        if src.suffix.lower() in (".heic", ".heif") and not HEIC_OK:
            print(f"  WARNING: skipping {src.name} -- install pillow-heif "
                  f"for HEIC support (pip install pillow-heif)")
            continue
        rel = f"{place}/{src.name}" if place else src.name
        thumb = out_dir / media_name(rel, "t")
        web = out_dir / media_name(rel, "w")
        expected_media.update({thumb.name, web.name})

        try:
            width, height, taken = read_photo_info(src)
            src_mtime = src.stat().st_mtime
            for dest, max_dim, quality in ((thumb, THUMB_MAX, THUMB_QUALITY),
                                           (web, WEB_MAX, WEB_QUALITY)):
                if not dest.exists() or dest.stat().st_mtime < src_mtime:
                    generate_derivative(src, dest, max_dim, quality)
                    generated += 1
        except Exception as exc:
            print(f"  WARNING: could not process {src.name}: {exc}")
            continue

        photos.append({
            "name": src.name,
            "place_key": place,
            "original": f"trips/{slug}/{rel}",
            "thumb": f"media/{slug}/{thumb.name}",
            "web": f"media/{slug}/{web.name}",
            "caption": captions.get(rel.lower(),
                                    captions.get(src.name.lower(), "")),
            "taken": taken.strftime("%Y-%m-%d %H:%M") if taken else "",
            "bytes": src.stat().st_size,
            "w": width,
            "h": height,
        })

    if not photos:
        return None

    # Remove derivatives whose source photo was deleted.
    if out_dir.exists():
        for stale in out_dir.iterdir():
            if stale.name not in expected_media:
                stale.unlink()
                print(f"  removed stale derivative: {stale.name}")

    # Order places: ungrouped photos first, then the "## Places" section's
    # order, then any remaining places chronologically by earliest photo.
    earliest = {}
    for p in photos:
        k = p["place_key"]
        earliest[k] = min(earliest.get(k, "9999"), p["taken"] or "9999")
    folders = [k for k in earliest if k]
    listed = []
    for wanted in place_order:
        match = next((f for f in folders if f.lower() == wanted), None)
        if match and match not in listed:
            listed.append(match)
    rest = sorted((f for f in folders if f not in listed),
                  key=lambda f: (earliest[f], f.lower()))
    rank = {f: i for i, f in enumerate(([""] if "" in earliest else [])
                                       + listed + rest)}
    photos.sort(key=lambda p: (rank[p["place_key"]],
                               p["taken"] or "9999", p["name"].lower()))

    def display_name(folder):
        if folder.lower() in place_names:
            return place_names[folder.lower()]
        pretty = re.sub(r"^\d+[-_ ]*", "", folder)
        return pretty.replace("-", " ").replace("_", " ").strip().title() \
            or folder

    for p in photos:
        key = p.pop("place_key")
        p["place"] = display_name(key) if key else ""

    # Trip sort date: front matter > earliest photo > folder name > today.
    sort_date = ""
    fm_date = meta.get("date", "")
    if re.match(r"^\d{4}-\d{2}(-\d{2})?$", fm_date):
        sort_date = fm_date
    if not sort_date:
        taken_dates = [p["taken"] for p in photos if p["taken"]]
        if taken_dates:
            sort_date = min(taken_dates)[:10]
    if not sort_date:
        fm = re.match(r"^(\d{4}-\d{2}(-\d{2})?)", slug)
        sort_date = fm.group(1) if fm else datetime.now().strftime("%Y-%m-%d")

    # Cover can be a bare filename or "place/filename".
    cover_name = meta.get("cover", "").strip().lower().replace("\\", "/")
    cover = photos[0]
    if cover_name:
        cover = next(
            (p for p in photos
             if p["name"].lower() == cover_name
             or p["original"].lower().endswith("/" + cover_name)),
            photos[0])

    if generated:
        print(f"  {slug}: {len(photos)} photos, "
              f"{generated} derivative(s) generated")

    return {
        "slug": slug,
        "title": meta.get("title") or slug,
        "location": meta.get("location", ""),
        "dates": meta.get("dates", ""),
        "sort_date": sort_date,
        "notes_md": notes_md,
        "cover": {"thumb": cover["thumb"], "web": cover["web"]},
        "photo_count": len(photos),
        "total_bytes": sum(p["bytes"] for p in photos),
        "photos": photos,
    }


# ---------------------------------------------------------------- build

def build():
    if not TRIPS_DIR.exists():
        TRIPS_DIR.mkdir()
    site = {"title": "Trips", "subtitle": "", "repo": ""}
    if SITE_CONFIG.exists():
        site.update(json.loads(SITE_CONFIG.read_text(encoding="utf-8")))

    trips = []
    slugs = set()
    for trip_dir in sorted(TRIPS_DIR.iterdir()):
        if trip_dir.is_dir() and not trip_dir.name.startswith("."):
            entry = process_trip(trip_dir)
            if entry:
                trips.append(entry)
                slugs.add(entry["slug"])
    trips.sort(key=lambda t: t["sort_date"], reverse=True)

    # Remove media folders for deleted trips.
    if MEDIA_DIR.exists():
        for folder in MEDIA_DIR.iterdir():
            if folder.is_dir() and folder.name not in slugs:
                for f in folder.iterdir():
                    f.unlink()
                folder.rmdir()
                print(f"  removed media for deleted trip: {folder.name}")

    manifest = {
        "site": site,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "trips": trips,
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")

    originals = sum(t["total_bytes"] for t in trips)
    media = sum(f.stat().st_size for f in MEDIA_DIR.rglob("*")
                if f.is_file()) if MEDIA_DIR.exists() else 0
    total_photos = sum(t["photo_count"] for t in trips)
    print(f"\nBuilt site: {len(trips)} trip(s), {total_photos} photo(s)")
    print(f"  originals: {human_size(originals)}   "
          f"web copies: {human_size(media)}")
    if originals + media > 900 * 1024 * 1024:
        print("  WARNING: approaching GitHub Pages' 1 GB site limit."
              "\n  Consider moving originals to GitHub Releases"
              " (see README.md).")
    return len(trips), total_photos


def publish(no_push=False, message=None):
    n_trips, n_photos = build()

    if no_push:
        print("\nSkipped git commit/push (--no-push).")
        return

    run_git(["add", "-A"])
    status = run_git(["status", "--porcelain"], capture=True).stdout.strip()
    if not status:
        print("\nNo changes to publish -- site is up to date.")
        return
    msg = message or f"Update trips ({n_trips} trips, {n_photos} photos)"
    run_git(["commit", "-m", msg])

    remote = run_git(["remote", "get-url", "origin"], capture=True)
    if remote.returncode != 0:
        print("\nCommitted locally. No 'origin' remote configured yet, "
              "so nothing was pushed.")
        return
    push = run_git(["push", "-u", "origin", "HEAD"], capture=True)
    if push.returncode != 0:
        print("\nCommitted locally, but push failed:")
        print(push.stderr.strip())
        return

    url = remote.stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    if m:
        owner, repo = m.group(1).lower(), m.group(2)
        print(f"\nPublished! Site updates in ~1 minute at: "
              f"https://{owner}.github.io/{repo}/")
    else:
        print("\nPublished!")


def new_trip(title, date=None):
    date = date or datetime.now().strftime("%Y-%m-%d")
    slug = f"{date[:7]}-{slugify(title)}"
    trip_dir = TRIPS_DIR / slug
    if trip_dir.exists():
        print(f"trips/{slug} already exists.")
        return
    trip_dir.mkdir(parents=True)
    (trip_dir / "notes.md").write_text(
        NOTES_TEMPLATE.format(title=title, date=date), encoding="utf-8")
    print(f"Created trips/{slug}/")
    print(f"  1. Copy your photos into that folder.")
    print(f"  2. Edit trips/{slug}/notes.md")
    print(f"  3. Run: python publish.py")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "new":
        parser = argparse.ArgumentParser(prog="publish.py new")
        parser.add_argument("title")
        parser.add_argument("--date", help="Trip start date (YYYY-MM-DD)")
        args = parser.parse_args(sys.argv[2:])
        new_trip(args.title, args.date)
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-push", action="store_true",
                        help="build only; skip git commit and push")
    parser.add_argument("-m", "--message", help="custom commit message")
    args = parser.parse_args()
    publish(no_push=args.no_push, message=args.message)


if __name__ == "__main__":
    main()
