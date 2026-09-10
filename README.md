# AE Territory Map

Interactive world map showing which Account Executive owns each country, based on the
**AE 2026** field of the *Country of HQ* database in the BDR + AE Regionalization wiki page.

Hover a country for its AE and region. Click an AE in the legend to isolate their patch.

**Live:** https://rarelyraul.github.io/ae-territory-map/

Served by GitHub Pages from the root of `main`. Push a new `index.html` and the live map
updates about a minute later, at the same URL.

## Maintenance

`index.html` is **generated** — don't hand-edit it. A GitHub Action re-reads the Notion
source every Monday, regenerates the map, and pushes only if the territories changed.

    python3 build.py --source notion            # regenerate (needs NOTION_TOKEN)
    python3 build.py --source notion --check    # exit 1 if the map is stale
    python3 build.py --source assignments.json  # rebuild offline from the last snapshot

- `template.html` — page shell (CSS/JS). Edit for design changes.
- `config.json` — colours, legend order, audit thresholds. Edit for who-is-what-colour.
- `geometry.json` — frozen country paths keyed by ISO alpha-2. The coastlines don't move,
  so geometry is never re-derived; only the country-to-AE mapping is refetched.

Every run audits itself and refuses to write on a truncated read, a country that lost its
AE, or an unrecognised AE group, rather than publishing a map with holes in it.

## Technical notes

- Fully self-contained: no CDN, no build step, no external requests. Just open the file.
- Geometry: Natural Earth 1:50m via `world-atlas`, simplified with `topojson-simplify`,
  pre-projected to Natural Earth I and inlined as SVG paths.
- 236 of 251 database rows are drawn; the rest are too small to render at this scale.
- Antarctica is deliberately excluded — no account HQs there, and it dominated the frame.
- France's outline includes its overseas departments (French Guiana, Guadeloupe,
  Martinique, Mayotte, Réunion), which the database assigns to other AEs. Gibraltar,
  Svalbard, Tokelau and Tuvalu are too small to render at this scale.
