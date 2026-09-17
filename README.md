# Trips — travel log & photo journal

A static photo journal hosted on GitHub Pages. Original photos are stored
untouched in this repo; a local script generates fast web-sized copies and
publishes everything with one command.

**Live site:** https://mlariwork.github.io/trips/

## Adding a trip

```
python publish.py new "Kyoto, Japan"
```

This creates `trips/2026-09-kyoto-japan/` with a `notes.md` template. Then:

1. **Copy your photos** into that folder (JPG, PNG, HEIC, WebP, TIFF all
   work). Originals are never modified or recompressed.
2. **Edit `notes.md`** — dates, location, notes, memories, and photo
   captions (see format below).
3. **Publish:**

   ```
   python publish.py
   ```

   (Or double-click `publish.bat`.) This generates thumbnails and viewing
   copies for any new photos, rebuilds the site data, commits, and pushes.
   The live site updates about a minute later.

You can also skip step 0 entirely: just create any folder under `trips/`,
drop photos in, and run `python publish.py` — a `notes.md` template is
created for you to fill in afterwards.

To add photos or edit notes for an existing trip, do it directly in the
trip's folder and run `python publish.py` again. To delete a photo or a
whole trip, delete the file/folder and publish — generated copies are
cleaned up automatically.

## notes.md format

```markdown
---
title: Kyoto, Japan
location: Kyoto, Japan
dates: May 3–12, 2024        <- free-form text shown on the site
date: 2024-05-03             <- YYYY-MM-DD, used to order trips (optional:
                                falls back to photo EXIF dates)
cover: IMG_0042.jpg          <- cover photo (optional: defaults to first photo)
---

Free-form notes, memories, and stories in Markdown.

## Photo captions

IMG_0042.jpg: Fushimi Inari at dawn, before the crowds
IMG_0080.jpg: Best bowl of ramen of the entire trip
```

The "Photo captions" section is optional and doesn't appear in the notes —
captions show up under each photo in the lightbox. Photos are ordered by the
date they were taken (from EXIF), falling back to filename.

## How it works

- `trips/<slug>/` — your originals + `notes.md`. Never touched by the script.
- `media/<slug>/` — generated thumbnails (800px) and viewing copies (2000px).
- `manifest.json` — generated site data (trip info, notes, photo lists).
- `index.html`, `trip.html`, `assets/` — the static site. GitHub Pages
  serves the repo root, so the "Download original" link in the lightbox
  serves your untouched original file.
- `site.json` — site title/subtitle; edit freely.

Only new or changed photos are reprocessed, so publishing is fast even as
the collection grows.

## Setup on a new machine

```
git clone https://github.com/MLARIWORK/trips.git
cd trips
python -m pip install -r requirements.txt
```

## Size limits

GitHub Pages serves sites up to ~1 GB, and this repo stores originals
directly, so that budget covers your full-quality photos (roughly 150–300
phone photos). `publish.py` reports total size on every run and warns as you
approach the limit. If the collection outgrows it, the structure supports
moving originals to GitHub Releases (2 GB per file, effectively unlimited
total) while the site keeps serving the high-quality 2000px copies —
ask Claude to migrate it when the warning appears.

## Local preview

```
python -m http.server 8123
```

Then open http://localhost:8123/.
