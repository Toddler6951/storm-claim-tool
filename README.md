# Storm Claim Tool

A web tool for forensic property-insurance research. Enter a project address,
get the proximity, intensity, and timing of historical NWS Local Storm Reports
(LSR) and NOAA Storm Events Database (SED) records around it. Outputs include
a sortable table, a map with concentric search rings, a dashboard, and a
downloadable Combined Events CSV / Excel report.

## Live site

After you deploy, the app is at:

```
https://YOUR-USERNAME.github.io/REPO-NAME/
```

(replace `YOUR-USERNAME` and `REPO-NAME` with your GitHub username and the
name of this repo.)

## How it works

| Source | What it is | How it's pulled |
| --- | --- | --- |
| **NWS LSR** | Real-time spotter reports collected by NWS Weather Forecast Offices. | Live from [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/) on every search. Goes back to ~2003. |
| **NOAA SED** | Finalized event records published by NCEI with a 2–4 month lag — authoritative for forensics. | Pre-fetched by `fetch_sed.py` (run on a monthly cron via GitHub Actions), split per state per year, served alongside the HTML. |

The two sources are merged on every search: SED is authoritative through its
latest BEGIN_DATE; LSR fills the gap after that. No double-counting.

## Files in this repo

| File | Purpose |
| --- | --- |
| `index.html` | The single-page app. All UI, parsing, map, charts, exports. |
| `fetch_sed.py` | Downloads NCEI bulk SED CSVs and splits them per state/year. |
| `.github/workflows/refresh-sed.yml` | GitHub Action: runs fetch_sed.py monthly and commits the result. |
| `sed-data/` | Per-state SED CSVs (auto-generated; do not edit by hand). |

## Quick deploy (you've probably already done this)

1. **Fork or clone this repo.**
2. **Settings → Pages →** Source: *Deploy from a branch*, Branch: `main` / `(root)`.
3. The first push triggers the SED refresh action automatically. Watch
   *Actions → Refresh SED data* to confirm it ran. Initial fetch takes
   ~10–20 minutes depending on how many years it pulls.
4. Visit `https://YOUR-USERNAME.github.io/REPO-NAME/` — that's your tool.

`SED_BASE_URL` is auto-detected from `window.location` — no need to edit
anything in `index.html`.

## Refreshing SED data

NCEI republishes the recent year(s) of SED roughly monthly as more events
get finalized. The included GitHub Action handles this:

- **Automatic**: 1st of every month, 06:00 UTC.
- **On demand**: Actions tab → *Refresh SED data* → *Run workflow*.

If a year hasn't been republished by NCEI since the last run, the script
skips it (a `sed-data/_manifest.json` tracks the latest creation date pulled
for each year).

## Local development

```bash
# Clone, then from the repo root:
python -m http.server 8000
# Open http://localhost:8000/ in a browser.
```

For local-only manual SED uploads, leave `SED_BASE_URL` empty (the auto-detect
returns `""` on localhost) and drag a SED CSV onto the upload box in the
sidebar.

## Custom domain

Add a `CNAME` file at the repo root containing one line: your domain
(e.g., `storm.example.com`). Then set up DNS at your registrar:

- For a subdomain like `storm.example.com`: add a `CNAME` record pointing to
  `YOUR-USERNAME.github.io`.
- For an apex domain like `example.com`: add `A` records pointing to GitHub
  Pages' four IPs (185.199.108.153, 185.199.109.153, 185.199.110.153,
  185.199.111.153).

In *Settings → Pages*, paste the domain into the *Custom domain* field and
enable *Enforce HTTPS* once GitHub provisions the cert (a few minutes).

## Limitations

- U.S. addresses only (Census Geocoder).
- LSR coverage starts ~2003; SED goes back to 1950 but is sparse pre-2000.
- `magnitude` is not always populated (e.g., damage-only wind reports).
- The "Likely damaging" heuristic was removed by design — damage cannot be
  inferred from event presence; check the actual remark/narrative.

## Data licensing

Data comes from NOAA / NWS, which is in the public domain. The HTML app code
is up to you to license — MIT is a reasonable default for personal use; check
NOAA's [data citation guidance](https://www.weather.gov/disclaimer) for
formal/commercial reuse.

## Credits

- Map: [Leaflet](https://leafletjs.com/) + [OpenStreetMap](https://www.openstreetmap.org/) tiles
- Charts: [Chart.js](https://www.chartjs.org/)
- Spreadsheet export: [SheetJS](https://sheetjs.com/)
- CSV parsing: [PapaParse](https://www.papaparse.com/)
- Image export: [html2canvas](https://html2canvas.hertzen.com/)
- Address autocomplete: [Photon](https://photon.komoot.io/)
- Geocoding: [U.S. Census Bureau](https://geocoding.geo.census.gov/)
- LSR data: [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/)
- SED data: [NCEI Storm Events Database](https://www.ncei.noaa.gov/stormevents/)
