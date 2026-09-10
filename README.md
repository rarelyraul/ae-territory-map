# AE Territory Map

Interactive world map showing which Account Executive owns each country, based on the
**AE 2026** field of the *Country of HQ* database in the BDR + AE Regionalization wiki page.

Hover a country for its AE and region. Click an AE in the legend to isolate their patch.

**Live:** https://rarelyraul.github.io/ae-territory-map/

Served by GitHub Pages from the root of `main`. Push a new `index.html` and the live map
updates about a minute later, at the same URL.

## Maintenance

The country-to-AE assignments are **baked into `index.html`** — it does not read live
from Notion. When territories change, the file needs regenerating and pushing.

## Technical notes

- Fully self-contained: no CDN, no build step, no external requests. Just open the file.
- Geometry: Natural Earth 1:50m via `world-atlas`, simplified with `topojson-simplify`
  (weight 0.1), pre-projected to Natural Earth I and inlined as SVG paths.
- 236 of 250 territories in the database are rendered.
- Antarctica is deliberately excluded — no account HQs there, and it dominated the frame.
- France's outline includes its overseas departments (French Guiana, Guadeloupe,
  Martinique, Mayotte, Réunion), which the database assigns to other AEs. Gibraltar,
  Svalbard, Tokelau and Tuvalu are too small to render at this scale.
