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
import html
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
        }
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
<link rel="stylesheet" href="/assets/style.css?v=1">
</head>
<body>
<header class="site-header">
  <a class="brand" href="/">Sujan Thapa <span>· Photos</span></a>
  <nav>
    <a href="/#albums">Albums</a>
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
  <button class="lb-close" aria-label="Close">×</button>
  <button class="lb-prev" aria-label="Previous">‹</button>
  <figure><img alt=""><figcaption></figcaption></figure>
  <button class="lb-next" aria-label="Next">›</button>
</div>
<script src="/assets/gallery.js?v=1"></script>
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

    # ---- home
    album_cards = "\n".join(
        f"""<a class="album-card" href="/albums/{a['slug']}/">
      <img src="{covers[a['slug']]['thumb']}" alt="{html.escape(a['name'])}" loading="lazy" width="{covers[a['slug']]['thumb_w']}" height="{covers[a['slug']]['thumb_h']}">
      <span class="album-meta"><strong>{html.escape(a['name'])}</strong><em>{a['count']} photos</em></span>
    </a>"""
        for a in albums
    )
    recent = sorted(all_photos.values(), key=lambda p: p["taken"], reverse=True)[:12]
    recent_figs = "\n".join(fig(p) for p in recent)
    home = (
        head("Sujan Thapa — Photos", f"Photography by Sujan Thapa — {total} photos in {len(albums)} albums.", hero["large"], "/")
        + f"""
<section class="hero">
  <img src="{hero['large']}" srcset="{hero['srcset']}" sizes="100vw" alt="{html.escape(hero['title'])}">
  <div class="hero-text"><h1>Photos</h1><p>{total} photographs · {len(albums)} albums · shot on whatever was in my hand, now a Fujifilm X100VI</p></div>
</section>
<section id="albums" class="wrap">
  <h2>Albums</h2>
  <div class="album-grid">{album_cards}</div>
</section>
<section class="wrap">
  <h2>Most recent</h2>
  <div class="grid">{recent_figs}</div>
</section>"""
        + FOOT
    )
    write("index.html", home)

    # ---- album + photo pages
    urls = ["/"]
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
        "generated": datetime.utcnow().isoformat() + "Z",
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
    return f"""<figure class="cell">
    <a href="/photos/{p['slug']}/" class="lb-item" data-large="{p['large']}" data-title="{html.escape(p['title'])}">
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
