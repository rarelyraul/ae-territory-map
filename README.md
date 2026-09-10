# AE Territory Map

Interactive world map showing which Account Executive owns each country, based on the
**AE 2026** field of the *Country of HQ* database in the BDR + AE Regionalization wiki page.

Hover a country for its AE and region. Click an AE in the legend to isolate their patch.

## Publishing this (GitHub Pages)

1. Create a new **public** repo — suggested name: `ae-territory-map`.
2. Upload `index.html` to the root of the repo (drag and drop into the web UI is fine).
3. Go to **Settings → Pages**.
4. Under *Build and deployment*, set **Source** = `Deploy from a branch`,
   **Branch** = `main`, folder = `/ (root)`. Save.
5. Wait ~1 minute. The site goes live at:

       https://<your-github-username>.github.io/ae-territory-map/

The repo must be public for Pages to work on a free GitHub plan.

## Embedding in Notion

On the BDR + AE Regionalization page, inside a toggle:

    /embed  →  paste the github.io URL above

## Maintenance

The country-to-AE assignments are **baked into `index.html`** — it does not read live
from Notion. When territories change, the file needs regenerating and re-uploading.

## Technical notes

- Fully self-contained: no CDN, no build step, no external requests. Just open the file.
- Geometry: Natural Earth 1:50m via `world-atlas`, simplified with `topojson-simplify`
  (weight 0.1), pre-projected to Natural Earth I and inlined as SVG paths.
- 236 of 250 territories in the database are rendered.
- Antarctica is deliberately excluded — no account HQs there, and it dominated the frame.
- France's outline includes its overseas departments (French Guiana, Guadeloupe,
  Martinique, Mayotte, Réunion), which the database assigns to other AEs. Gibraltar,
  Svalbard, Tokelau and Tuvalu are too small to render at this scale.
