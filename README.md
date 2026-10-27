# photos.sujanthapa.com

Static photo gallery. **Flickr is the source of truth** — the site is
generated from Flickr at build time; nothing calls the Flickr API when
someone visits a page, and no API key is shipped to visitors.

## How it works

- Upload / organise photos on Flickr as usual (albums = galleries here).
- `tools/build.py` fetches every album, photo, size and EXIF via the
  Flickr API and regenerates the whole site: `index.html`,
  `albums/<slug>/`, `photos/<slug>/` (one page per photo),
  `data/photos.json`, `sitemap.xml`.
- A GitHub Action (`.github/workflows/refresh.yml`) does this weekly
  and on demand, committing only when Flickr changed. It needs one repo
  secret: `FLICKR_API_KEY` (the public read-only Flickr API key).
- GitHub Pages serves the result at photos.sujanthapa.com (see `CNAME`).
  `.nojekyll` — this is no longer a Jekyll site.

## Run it locally

```sh
FLICKR_API_KEY=xxxx python3 tools/build.py
python3 -m http.server   # preview at http://localhost:8000
```

New Flickr albums are picked up automatically (slug = slugified
title). The four long-standing albums keep their existing slugs.

## Layout

- `tools/build.py` — the generator (the only code that matters)
- `assets/` — hand-written CSS + lightbox JS
- Everything else at the root is generated output — don't hand-edit it;
  change the generator or Flickr instead.
