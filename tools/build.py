#!/usr/bin/env python3
"""
Build photos.sujanthapa.com from Flickr at BUILD time.

Flickr is the backend / source of truth: upload there, then run this
script (locally or via the refresh GitHub Action) and it regenerates
the whole static site — home, album pages, one page per photo,
sitemap, and data/photos.json. Nothing calls the Flickr API at
page-view time, and no API key ships to visitors.

Usage:
    FLICKR_API_KEY=xxxx python3 tools/build.py

The key is the same (public, read-only) key the old site embedded in
its JavaScript. In CI it is supplied from the FLICKR_API_KEY repo
secret. Never hardcode a different/secret key here.
"""
import colorsys
import html
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.flickr.com/services/rest/"
USER_ID = "145373894@N07"  # sujanthapa
SITE = "https://photos.sujanthapa.com"
HERO_PHOTO_ID = "30582166924"  # "Focused on strings" — the old homepage hero
# Story-hero rotation on the home page (experiment 01 from the demo).
FEATURED_IDS = ["30582166924", "30790679834", "31278222750", "33442529120", "31671225123"]


def dominant_color(url):
    """Average colour of an image URL as #rrggbb, or '' if unavailable
    (Pillow missing / fetch failed) — colour features degrade quietly."""
    try:
        from PIL import Image

        with urllib.request.urlopen(url, timeout=20) as r:
            im = Image.open(io.BytesIO(r.read())).convert("RGB").resize((24, 24))
        px = list(im.getdata())
        n = len(px)
        return "#%02x%02x%02x" % (
            sum(c[0] for c in px) // n,
            sum(c[1] for c in px) // n,
            sum(c[2] for c in px) // n,
        )
    except Exception:
        return ""


def exif_line(exif):
    bits = []
    if exif.get("Camera"):
        bits.append(exif["Camera"])
    if exif.get("Lens"):
        bits.append(exif["Lens"])
    if exif.get("Aperture"):
        bits.append("ƒ/" + re.sub(r"[^0-9.]", "", exif["Aperture"]))
    if exif.get("Exposure"):
        bits.append(exif["Exposure"])
    if exif.get("ISO"):
        bits.append("ISO " + re.sub(r"[^0-9]", "", exif["ISO"]))
    if exif.get("Focal length"):
        bits.append(exif["Focal length"])
    return " · ".join(bits)

# Album order + slugs. New Flickr albums are picked up automatically
# and appended after these, slugified from their title.
KNOWN_ALBUMS = [
    ("72157679185664076", "airplanes"),
    ("72157678013410115", "nature"),
    ("72157676384739461", "architecture"),
    ("72157673898069703", "miscellaneous"),
]


def api(key, method, **params):
    q = urllib.parse.urlencode(
        {"format": "json", "nojsoncallback": 1, "method": method, "api_key": key, **params}
    )
    with urllib.request.urlopen(API + "?" + q, timeout=30) as r:
        data = json.loads(r.read())
    if data.get("stat") != "ok":
        raise RuntimeError(f"{method} failed: {data.get('message')}")
    return data


def slugify(text, fallback):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or fallback


def pick_size(sizes, label_preference):
    by_label = {s["label"]: s for s in sizes}
    for lab in label_preference:
        if lab in by_label:
            return by_label[lab]
    return sizes[-1] if sizes else None


EXIF_WANTED = {
    "Model": "Camera",
    "LensModel": "Lens",
    "ExposureTime": "Exposure",
    "FNumber": "Aperture",
    "ISOSpeedRatings": "ISO",
    "FocalLength": "Focal length",
}


def fetch(key):
    sets_data = api(key, "flickr.photosets.getList", user_id=USER_ID)
    sets = {s["id"]: s for s in sets_data["photosets"]["photoset"]}
    ordered_ids = [sid for sid, _ in KNOWN_ALBUMS if sid in sets]
    ordered_ids += [sid for sid in sets if sid not in ordered_ids]

    def build_photo(p, album_name, album_slug):
        pid = p["id"]
        if pid in all_photos:
            return all_photos[pid]  # a photo can live in two Flickr albums
        sizes = api(key, "flickr.photos.getSizes", photo_id=pid)["sizes"]["size"]
        thumb = pick_size(sizes, ["Medium", "Small 320", "Small"])
        large = pick_size(sizes, ["Large 2048", "Large 1600", "Large", "Original"])
        huge = pick_size(sizes, ["Original", "Large 2048", "Large 1600", "Large"])
        exif_out = {}
        try:
            ex = api(key, "flickr.photos.getExif", photo_id=pid)
            camera = ex.get("photo", {}).get("camera")
            raw = {}
            for e in ex.get("photo", {}).get("exif", []):
                raw[e["tag"]] = (e.get("clean") or e.get("raw") or {}).get("_content", "")
            if camera:
                exif_out["Camera"] = camera
            for tag, label in EXIF_WANTED.items():
                if tag in raw and label not in exif_out:
                    exif_out[label] = raw[tag]
        except Exception:
            pass  # EXIF is a nice-to-have, never a build blocker
        photo = {
            "id": pid,
            "title": p.get("title") or "Untitled",
            "slug": f"{pid}-{slugify(p.get('title'), 'photo')}",
            "album": album_name,
            "album_slug": album_slug,
            "taken": p.get("datetaken", ""),
            "description": (p.get("description") or {}).get("_content", "")
            if isinstance(p.get("description"), dict)
            else (p.get("description") or ""),
            "thumb": thumb["source"] if thumb else "",
            "thumb_w": int(thumb["width"]) if thumb else 0,
            "thumb_h": int(thumb["height"]) if thumb else 0,
            "large": large["source"] if large else "",
            "large_w": int(large["width"]) if large else 0,
            "large_h": int(large["height"]) if large else 0,
            "full": huge["source"] if huge else "",
            "srcset": ", ".join(
                f"{sz['source']} {sz['width']}w"
                for sz in sizes
                if sz["label"] in ("Small 320", "Medium", "Medium 640", "Large")
                and int(sz["width"]) >= 240
            ),
            "flickr_url": f"https://www.flickr.com/photos/{USER_ID}/{pid}/",
            "exif": exif_out,
            "exif_line": exif_line(exif_out),
        }
        photo["color"] = dominant_color(photo["thumb"]) if photo["thumb"] else ""
        all_photos[pid] = photo
        print(f"  {album_name}: {photo['title']} ({pid})", file=sys.stderr)
        return photo

    albums, all_photos = [], {}
    for sid in ordered_ids:
        s = sets[sid]
        slug = dict(KNOWN_ALBUMS).get(sid) or slugify(s["title"]["_content"], sid)
        resp = api(
            key,
            "flickr.photosets.getPhotos",
            photoset_id=sid,
            extras="url_m,url_l,date_taken,description,tags",
            per_page=500,
        )
        photos = [build_photo(p, s["title"]["_content"], slug) for p in resp["photoset"]["photo"]]
        albums.append(
            {
                "id": sid,
                "name": s["title"]["_content"],
                "slug": slug,
                "count": len(photos),
                "primary": s.get("primary"),
                "photos": photos,
            }
        )

    # Public photos not in any album get an "Unfiled" album, so a fresh
    # Flickr upload shows up on the site even before it's organised —
    # and nothing on Flickr is ever missing from the gallery.
    in_albums = {p["id"] for a in albums for p in a["photos"]}
    stream = api(
        key, "flickr.people.getPhotos", user_id=USER_ID,
        extras="date_taken,description", per_page=500,
    )
    stray = [p for p in stream["photos"]["photo"] if p["id"] not in in_albums]
    if stray:
        photos = [build_photo(p, "Unfiled", "unfiled") for p in stray]
        albums.append(
            {"id": "unfiled", "name": "Unfiled", "slug": "unfiled",
             "count": len(photos), "primary": photos[0]["id"], "photos": photos}
        )
    return albums, all_photos


# ---------------------------------------------------------------- templates

def head(title, desc, image, path):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{SITE}{path}">
<meta property="og:type" content="website">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{html.escape(image)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📷</text></svg>">
<link rel="stylesheet" href="/assets/style.css?v=2">
<script>try{{if(localStorage.getItem("photos-theme")==="dark")document.documentElement.dataset.theme="dark"}}catch(e){{}}</script>
</head>
<body>
<header class="site-header">
  <a class="brand" href="/">Sujan Thapa <span>· Photos</span></a>
  <nav>
    <a href="/#albums">Albums</a>
    <a href="/colour/">Colour</a>
    <button id="themeBtn" class="theme-btn" type="button" aria-label="Toggle darkroom mode">🌑</button>
    <a href="https://sujanthapa.com">Main site</a>
    <a href="https://www.flickr.com/photos/{USER_ID}/">Flickr</a>
    <a href="https://vsco.co/najus">VSCO</a>
    <a href="https://instagram.com/najusphoto">Instagram</a>
  </nav>
</header>
<main>
"""


FOOT = """
</main>
<footer class="site-footer">
  <p>Photographs by Sujan Thapa. Hosted on Flickr, published here as a static site —
  rebuilt automatically from Flickr by <code>tools/build.py</code>.</p>
  <p><a href="https://sujanthapa.com">sujanthapa.com</a> · <a href="https://www.flickr.com/photos/145373894@N07/">Flickr</a> · <a href="https://vsco.co/najus">VSCO</a></p>
</footer>
<div class="lightbox" id="lightbox" hidden>
  <div class="lb-glow"></div>
  <span class="lb-count"></span>
  <button class="lb-close" aria-label="Close">×</button>
  <button class="lb-prev" aria-label="Previous">‹</button>
  <figure><img alt=""><figcaption><strong class="lb-title"></strong><span class="lb-exif"></span></figcaption></figure>
  <button class="lb-next" aria-label="Next">›</button>
  <div class="lb-strip"></div>
</div>
<script src="/assets/gallery.js?v=2"></script>
</body>
</html>
"""


def render(albums, all_photos):
    total = len(all_photos)  # unique photos; an album entry can repeat across albums
    hero = all_photos.get(HERO_PHOTO_ID) or albums[0]["photos"][0]
    covers = {}
    for a in albums:
        prim = next((p for p in a["photos"] if p["id"] == a["primary"]), a["photos"][0] if a["photos"] else None)
        covers[a["slug"]] = prim

    # ---- home: story hero (01) + editorial album index (02)
    featured = [all_photos[i] for i in FEATURED_IDS if i in all_photos] or [hero]
    story_json = json.dumps(
        [
            {
                "large": p["large"],
                "srcset": p["srcset"],
                "title": p["title"],
                "meta": p["album"] + ((" — " + p["exif_line"]) if p["exif_line"] else ""),
                "href": f"/photos/{p['slug']}/",
            }
            for p in featured
        ]
    )
    index_rows = "\n".join(
        f"""<a class="index-row" href="/albums/{a['slug']}/" data-cover="{covers[a['slug']]['thumb']}">
      <span class="no">{i + 1:02d}</span><span class="name">{html.escape(a['name'])}</span>
      <span class="cnt">{a['count']} photos</span><span class="arr">→</span></a>"""
        for i, a in enumerate(albums)
    )
    recent = sorted(all_photos.values(), key=lambda p: p["taken"], reverse=True)[:12]
    recent_figs = "\n".join(fig(p) for p in recent)
    home = (
        head("Sujan Thapa — Photos", f"Photography by Sujan Thapa — {total} photos in {len(albums)} albums.", hero["large"], "/")
        + f"""
<section class="story" id="story">
  <img id="storyImg" src="{featured[0]['large']}" srcset="{featured[0]['srcset']}" sizes="100vw" alt="{html.escape(featured[0]['title'])}">
  <div class="story-shade"></div>
  <div class="story-segs" id="storySegs"></div>
  <div class="story-cap"><p class="story-kicker">Photos · {total} photographs · {len(albums)} albums</p><h1 id="storyTitle">{html.escape(featured[0]['title'])}</h1><p id="storyMeta"></p></div>
  <span class="story-count" id="storyCount"></span>
</section>
<script>window.STORY = {story_json};</script>
<section id="albums" class="wrap">
  <h2>Albums</h2>
  <div class="index-list">{index_rows}</div>
  <div class="cursor-preview" id="cursorPreview"><img alt=""></div>
</section>
<section class="wrap">
  <h2>Most recent</h2>
  <div class="grid">{recent_figs}</div>
</section>"""
        + FOOT
    )
    write("index.html", home)

    # ---- colour story page (06): whole archive sorted by dominant colour
    def hue_key(p):
        c = p.get("color") or "#000000"
        r, g, b = (int(c[i : i + 2], 16) / 255 for i in (1, 3, 5))
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        return (h, v)

    wall = "\n".join(
        f"""<a href="/photos/{p['slug']}/" style="background:{p.get('color') or '#888'}" title="{html.escape(p['title'])} — {p.get('color') or ''}">
      <img src="{p['thumb']}" alt="{html.escape(p['title'])}" loading="lazy"></a>"""
        for p in sorted(all_photos.values(), key=hue_key)
    )
    colour_page = (
        head("Colour — Sujan Thapa Photos", "The whole archive sorted by dominant colour.", hero["large"], "/colour/")
        + f"""
<section class="wrap">
  <p class="crumb"><a href="/">Photos</a> / Colour</p>
  <h1>Colour story</h1>
  <p class="sub">All {total} photographs, sorted by their dominant colour. Hover a swatch to peek; click to open the photo.</p>
  <div class="colour-wall">{wall}</div>
</section>"""
        + FOOT
    )
    write("colour/index.html", colour_page)

    # ---- album + photo pages
    urls = ["/", "/colour/"]
    rendered_photos = set()
    for a in albums:
        figs = "\n".join(fig(p) for p in a["photos"])
        page = (
            head(f"{a['name']} — Sujan Thapa Photos", f"{a['count']} photos in {a['name']}, by Sujan Thapa.", covers[a["slug"]]["large"], f"/albums/{a['slug']}/")
            + f"""
<section class="wrap">
  <p class="crumb"><a href="/">Photos</a> / {html.escape(a['name'])}</p>
  <h1>{html.escape(a['name'])}</h1>
  <p class="sub">{a['count']} photos</p>
  <div class="grid">{figs}</div>
</section>"""
            + FOOT
        )
        write(f"albums/{a['slug']}/index.html", page)
        urls.append(f"/albums/{a['slug']}/")
        for i, p in enumerate(a["photos"]):
            if p["slug"] in rendered_photos:
                continue  # already has a page from its first album
            rendered_photos.add(p["slug"])
            prev_p = a["photos"][i - 1] if i > 0 else None
            next_p = a["photos"][i + 1] if i < len(a["photos"]) - 1 else None
            exif_rows = "".join(
                f"<div><dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd></div>" for k, v in p["exif"].items()
            )
            taken = ""
            if p["taken"]:
                try:
                    taken = datetime.strptime(p["taken"], "%Y-%m-%d %H:%M:%S").strftime("%B %d, %Y")
                except ValueError:
                    taken = p["taken"]
            nav = ""
            if prev_p:
                nav += f'<a href="/photos/{prev_p["slug"]}/">‹ {html.escape(prev_p["title"])}</a>'
            if next_p:
                nav += f'<a class="next" href="/photos/{next_p["slug"]}/">{html.escape(next_p["title"])} ›</a>'
            page = (
                head(f"{p['title']} — Sujan Thapa Photos", p["description"] or f"{p['title']}, from the {a['name']} album by Sujan Thapa.", p["large"], f"/photos/{p['slug']}/")
                + f"""
<section class="wrap photo-page">
  <p class="crumb"><a href="/">Photos</a> / <a href="/albums/{a['slug']}/">{html.escape(a['name'])}</a></p>
  <h1>{html.escape(p['title'])}</h1>
  <p class="sub">{taken}</p>
  <img class="full" src="{p['large']}" srcset="{p['srcset']}" sizes="(max-width: 900px) 100vw, 1100px" alt="{html.escape(p['title'])}" width="{p['large_w']}" height="{p['large_h']}">
  {"<p class='desc'>" + html.escape(p["description"]) + "</p>" if p["description"] else ""}
  {"<dl class='exif'>" + exif_rows + "</dl>" if exif_rows else ""}
  <p class="flickr-link"><a href="{p['flickr_url']}">View on Flickr</a> · <a href="{p['full']}">Full size</a></p>
  <nav class="prevnext">{nav}</nav>
</section>"""
                + FOOT
            )
            write(f"photos/{p['slug']}/index.html", page)
            urls.append(f"/photos/{p['slug']}/")

    # ---- manifest, sitemap, robots
    manifest = {
        # No timestamp here on purpose: identical Flickr data must
        # produce an identical file, so the refresh Action can tell
        # "nothing changed" and skip committing.
        "source": "Flickr",
        "user_id": USER_ID,
        "total_photos": total,
        "albums": [{k: v for k, v in a.items() if k != "photos"} | {"photos": a["photos"]} for a in albums],
    }
    write("data/photos.json", json.dumps(manifest, indent=1))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{SITE}{u}</loc></url>" for u in urls]
    sm.append("</urlset>")
    write("sitemap.xml", "\n".join(sm))
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    return total


def fig(p):
    return f"""<figure class="cell" style="background:{p.get('color') or '#ddd'}">
    <a href="/photos/{p['slug']}/" class="lb-item" data-large="{p['large']}" data-title="{html.escape(p['title'])}" data-exif="{html.escape(p['exif_line'])}" data-color="{p.get('color') or ''}" data-album="{html.escape(p['album'])}">
      <img src="{p['thumb']}" srcset="{p['srcset']}" sizes="(max-width: 700px) 50vw, 400px" alt="{html.escape(p['title'])}" loading="lazy" width="{p['thumb_w']}" height="{p['thumb_h']}">
    </a>
    <figcaption>{html.escape(p['title'])}</figcaption>
  </figure>"""


def write(rel, content):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def main():
    key = os.environ.get("FLICKR_API_KEY")
    if not key:
        sys.exit("FLICKR_API_KEY is not set — see the docstring at the top of this file.")
    print("Fetching from Flickr…", file=sys.stderr)
    albums, all_photos = fetch(key)
    total = render(albums, all_photos)
    print(f"Built {total} photos in {len(albums)} albums.")


if __name__ == "__main__":
    main()
