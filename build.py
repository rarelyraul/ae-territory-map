#!/usr/bin/env python3
"""Regenerate the AE territory map from the Notion source of truth.

    python3 build.py --source notion          # live read (needs NOTION_TOKEN)
    python3 build.py --source assignments.json  # replay a saved snapshot
    python3 build.py --source notion --check    # fail if the map is out of date, write nothing

The country geometry never changes, so it is not re-derived: geometry.json holds
240 pre-projected SVG paths, each pinned to an ISO 3166-1 alpha-2 code. Only the
country -> AE mapping is refetched, and it is joined on that code. Nothing here
does fuzzy name matching, because that is how ~15 rows were silently dropped the
first time this map was built by hand.

Every run audits itself against config.json's "expectations" and exits non-zero
rather than quietly shipping a map with holes in it.
"""

import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
NOTION_VERSION = "2022-06-28"


def fail(msg):
    print("BUILD FAILED: %s" % msg, file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- Notion read

def fetch_from_notion(cfg):
    """Return [{iso2, country, aes: [...], region}] read live from the database."""
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        fail("NOTION_TOKEN is not set. Create an internal integration at\n"
             "  https://www.notion.so/profile/integrations\n"
             "share the 'Country of HQ' database with it, then export the secret as\n"
             "NOTION_TOKEN. Or run against a saved snapshot: --source assignments.json")

    nc = cfg["notion"]
    url = "https://api.notion.com/v1/databases/%s/query" % nc["database_id"]
    headers = {
        "Authorization": "Bearer %s" % token,
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    rows, cursor, pages = [], None, 0
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            if e.code in (401, 403):
                fail("Notion rejected the token (HTTP %d). Is the database shared with the\n"
                     "integration? Connections -> add your integration on the database.\n%s"
                     % (e.code, detail))
            fail("Notion query failed (HTTP %d): %s" % (e.code, detail))
        except urllib.error.URLError as e:
            fail("Could not reach Notion: %s" % e.reason)

        for page in payload["results"]:
            rows.append(_row_from_page(page["properties"], nc))
        pages += 1
        if not payload.get("has_more"):
            break
        cursor = payload["next_cursor"]

    _apply_iso_fixes(rows, cfg)
    print("Notion: %d rows over %d request(s)" % (len(rows), pages))
    return rows


def _apply_iso_fixes(rows, cfg):
    """Repair the handful of bad/blank Alpha-2 Codes so the join stays a code lookup."""
    remap = cfg.get("iso2_fixes", {})
    by_name = cfg.get("iso2_by_country_name", {})
    for r in rows:
        if not r["iso2"] and r["country"] in by_name:
            r["iso2"] = by_name[r["country"]]
        elif r["iso2"] in remap:
            r["iso2"] = remap[r["iso2"]]
    return rows


def _plain(prop):
    """Flatten a title/rich_text property to a plain string."""
    if not prop:
        return ""
    parts = prop.get("title") or prop.get("rich_text") or []
    return "".join(p.get("plain_text", "") for p in parts).strip()


def _row_from_page(props, nc):
    ae = [o["name"] for o in (props.get(nc["ae_property"], {}) or {}).get("multi_select", [])]
    region_prop = (props.get(nc["region_property"], {}) or {}).get("select")
    return {
        "iso2": _plain(props.get(nc["iso2_property"])).upper(),
        "country": _plain(props.get(nc["country_property"])),
        "aes": ae,
        "region": (region_prop or {}).get("name", "") if region_prop else "",
    }


# ------------------------------------------------------------- grouping logic

def group_key(aes):
    """Canonical, order-independent key for a set of AEs sharing a country."""
    return " & ".join(sorted(aes))


def resolve_groups(rows, cfg):
    """Assign a code and colour to every distinct AE group found in the data."""
    known = cfg["groups"]
    spare = list(cfg["fallback_colours"])
    groups, warnings = {}, []

    # Deterministic order so codes never shuffle between runs.
    seen = sorted({group_key(r["aes"]) for r in rows if r["aes"]})
    used_codes = {g["code"] for g in known.values()}

    for key in seen:
        if key in known:
            groups[key] = dict(known[key])
            continue
        # A new or renamed AE. Colour it rather than crash, but say so loudly.
        colour = spare.pop(0) if spare else "#888888"
        code = _free_code(key, used_codes)
        used_codes.add(code)
        groups[key] = {"colour": colour, "code": code}
        warnings.append(key)

    for key in known:
        if key not in groups:
            warnings.append("!gone: %s" % key)

    return groups, warnings


def _free_code(key, used):
    for ch in key.upper():
        if ch.isalpha() and ch not in used:
            return ch
    for ch in "ZYXWVUTSRQPONMLKJIHGFEDCBA":
        if ch not in used:
            return ch
    fail("ran out of single-letter group codes")


def build_legend(groups, cfg):
    """One row per person. Someone owning two groups gets one row carrying both."""
    person_groups = defaultdict(list)
    for key, g in groups.items():
        names = [g["label"]] if g.get("pool") else key.split(" & ")
        for name in names:
            person_groups[name].append(key)

    order = cfg["legend_order"]
    people = sorted(person_groups, key=lambda p: (order.index(p) if p in order else 999, p))

    rows = []
    for person in people:
        keys = sorted(person_groups[person], key=lambda k: -len(k.split(" & ")))
        codes = [groups[k]["code"] for k in keys]
        swatches = [groups[k]["colour"] for k in keys]
        shared_only = all(len(k.split(" & ")) > 1 and not groups[k].get("pool") for k in keys)
        rows.append({
            "person": person,
            "codes": codes,
            "swatches": swatches,
            "shared": shared_only,
        })
    return rows


# --------------------------------------------------------------------- render

def attr(text):
    """Escape for a double-quoted HTML attribute, leaving apostrophes alone.
    Matches the escaping the original hand-built file used, so regenerating an
    unchanged map produces an unchanged file."""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


REGION_ROLLUP = [
    (["UK&I"], "UK & Ireland"),
    (["Benelux"], "Benelux"),
    (["DACH"], "DACH"),
    (["Nordics", "Baltics", "Eastern Europe"], "Nordics, Baltics, Eastern Europe"),
    (["Southern Europe"], "Southern Europe"),
    (["Middle East", "Africa"], "Middle East, Africa"),
    (["East Asia", "Southeast Asia", "South Asia", "Central Asia",
      "Oceania/Pacific", "Australasia"], "APAC"),
    (["North America", "South America"], "North & South America"),
]


def summarise_regions(regions):
    """Collapse a pile of database regions into a short legend phrase."""
    present = set(regions)
    parts = []
    for members, label in REGION_ROLLUP:
        if present & set(members):
            parts.append(label)
    return ", ".join(parts) if parts else ""


def render(geometry, rows, groups, legend, cfg):
    by_iso = {}
    for r in rows:
        if r["iso2"]:
            by_iso[r["iso2"]] = r

    code_regions = defaultdict(list)
    # Tooltip text: always the individual AEs, even for a pool whose legend row
    # is a collective label - hovering a country should name who actually owns it.
    code_people = {}
    for key, g in groups.items():
        people = key.split(" & ")
        code_people[g["code"]] = ", ".join(people) if g.get("pool") else " & ".join(people)

    svg, rendered_iso, unassigned = [], set(), []
    for p in geometry["paths"]:
        row = by_iso.get(p["iso2"]) if p["iso2"] else None
        if row is None or not row["aes"]:
            unassigned.append(p["n"])
            svg.append('<path class=c d="%s" fill="%s" data-n="%s"/>'
                       % (p["d"], cfg["unassigned_colour"], attr(p["n"])))
            continue
        g = groups[group_key(row["aes"])]
        rendered_iso.add(p["iso2"])
        if row["region"] not in code_regions[g["code"]]:
            code_regions[g["code"]].append(row["region"])
        svg.append('<path class=c d="%s" fill="%s" data-n="%s" data-g="%s" data-r="%s"/>'
                   % (p["d"], g["colour"], attr(p["n"]),
                      g["code"], attr(row["region"])))

    lg = []
    for row in legend:
        sws = "".join('<span class=sw style="background:%s"></span>' % c for c in row["swatches"])
        region = summarise_regions(
            [r for c in row["codes"] for r in code_regions.get(c, [])])
        if row["shared"]:
            region += cfg["shared_suffix"]
        lg.append('<div class=row role=button tabindex=0 aria-pressed=false data-g="%s">'
                  '<span class=sws>%s</span><span class=lb><b>%s</b> <i>%s</i></span></div>'
                  % (" ".join(row["codes"]), sws,
                     attr(row["person"]), attr(region)))

    names_js = json.dumps(code_people, ensure_ascii=False, separators=(",", ":"))

    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    out = (tpl.replace("<!--PATHS-->", "".join(svg))
              .replace("<!--LEGEND-->", '<div id=lg>%s</div>' % "".join(lg))
              .replace("/*NAMES*/", names_js)
              .replace("{{VIEWBOX}}", geometry["viewBox"]))
    return out, rendered_iso, unassigned, code_regions


def render_csv(rows, groups):
    """The flat table, for Datawrapper/Flourish or anyone who wants a spreadsheet.

    ISO3 comes from iso3.json because the Notion database only carries alpha-2,
    and ISO3 is what most mapping tools match on.
    """
    iso3 = json.load(open(os.path.join(HERE, "iso3.json"), encoding="utf-8"))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["ISO3", "ISO2", "Country", "AE group", "AE", "Region"])
    for r in sorted(rows, key=lambda r: r["country"]):
        if r["aes"]:
            key = group_key(r["aes"])
            grp = groups[key].get("label", key)
            ae = " / ".join(r["aes"])
        else:
            grp = ae = ""
        w.writerow([iso3.get(r["iso2"], ""), r["iso2"], r["country"], grp, ae, r["region"]])
    return buf.getvalue()


# ----------------------------------------------------------------- self-audit

def audit(rows, rendered_iso, unassigned, groups, warnings, cfg):
    exp = cfg["expectations"]
    problems, notes = [], []

    if len(rows) < exp["min_countries_in_notion"]:
        problems.append("Notion returned %d countries, expected at least %d. Refusing to "
                        "publish a map built from a truncated read."
                        % (len(rows), exp["min_countries_in_notion"]))

    no_ae = [r["country"] for r in rows if not r["aes"]]
    if no_ae:
        notes.append("%d database rows have no AE 2026 value: %s"
                     % (len(no_ae), ", ".join(sorted(no_ae)[:10])))

    unexpected = sorted(set(unassigned) - set(exp["unassigned_paths_allowed"]))
    if unexpected:
        problems.append("%d countries would render grey but are not on the allowed list: %s. "
                        "Either they lost their AE in Notion, or an ISO code changed."
                        % (len(unexpected), ", ".join(unexpected)))

    missing_iso = [r["country"] for r in rows if not r["iso2"]]
    if missing_iso:
        notes.append("%d rows have no Alpha-2 Code so cannot be placed on the map: %s"
                     % (len(missing_iso), ", ".join(sorted(missing_iso))))

    in_db = {r["iso2"] for r in rows if r["iso2"] and r["aes"]}
    not_rendered = sorted(in_db - rendered_iso)
    new_not_rendered = sorted(set(not_rendered) - set(exp["known_not_rendered"]))
    if new_not_rendered:
        notes.append("%d assigned countries have no polygon at this scale and are newly "
                     "unrendered: %s" % (len(new_not_rendered), ", ".join(new_not_rendered)))

    for w in warnings:
        if w.startswith("!gone: "):
            notes.append("config.json lists group %r which no longer appears in Notion"
                         % w[len("!gone: "):])
        else:
            problems.append("AE group %r is in Notion but not in config.json, so it was given "
                            "a fallback colour. Add it to config.json to choose one." % w)

    print("\n--- audit ---")
    print("  countries in Notion      %d" % len(rows))
    print("  with an AE assigned      %d" % len(in_db))
    print("  drawn on the map         %d" % len(rendered_iso))
    print("  drawn but unassigned     %d  (%s)" % (len(unassigned), ", ".join(unassigned)))
    print("  assigned, too small      %d" % len(not_rendered))
    print("  AE groups                %d" % len(groups))
    for n in notes:
        print("  note: %s" % n)
    if problems:
        print()
        for p in problems:
            print("  PROBLEM: %s" % p, file=sys.stderr)
        fail("%d problem(s) above. Nothing was written." % len(problems))
    print("  ok\n")


# ------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="notion",
                    help="'notion' for a live read, or a path to a saved assignments.json")
    ap.add_argument("--check", action="store_true",
                    help="report whether the output would change; write nothing")
    ap.add_argument("--snapshot", default="assignments.json",
                    help="where to save the raw Notion read (default assignments.json)")
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    geometry = json.load(open(os.path.join(HERE, "geometry.json"), encoding="utf-8"))

    if args.source == "notion":
        rows = fetch_from_notion(cfg)
    else:
        rows = json.load(open(args.source, encoding="utf-8"))["countries"]
        _apply_iso_fixes(rows, cfg)
        print("Replaying %d rows from %s" % (len(rows), args.source))

    groups, warnings = resolve_groups(rows, cfg)
    legend = build_legend(groups, cfg)
    out, rendered_iso, unassigned, _ = render(geometry, rows, groups, legend, cfg)
    audit(rows, rendered_iso, unassigned, groups, warnings, cfg)

    index_path = os.path.join(HERE, "index.html")
    csv_path = os.path.join(HERE, "ae-territories.csv")
    new_csv = render_csv(rows, groups)

    old = open(index_path, encoding="utf-8").read() if os.path.exists(index_path) else ""
    changed = (old != out)

    if args.check:
        print("index.html would %s" % ("CHANGE" if changed else "be unchanged"))
        sys.exit(1 if changed else 0)

    if changed:
        open(index_path, "w", encoding="utf-8").write(out)
        print("wrote index.html (%d bytes)" % len(out))
    else:
        print("index.html already up to date")
    open(csv_path, "w", encoding="utf-8-sig", newline="").write(new_csv)
    if args.source == "notion":
        json.dump({"countries": rows}, open(os.path.join(HERE, args.snapshot), "w",
                  encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
        print("wrote %s" % args.snapshot)


if __name__ == "__main__":
    main()
