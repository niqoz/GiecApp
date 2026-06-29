#!/usr/bin/env python3
"""Build the static climate JSON used by the PWA.

Default target:
NASA NEX-GDDP-CMIP6 v2.0, ACCESS-CM2, r1i1p1f1, tasmax, France metropolitaine
+ Corse, years 2030..2100 every 5 years, scenarios ssp126/ssp245/ssp585.

The full build needs numpy + netCDF4 and downloads 45 annual NetCDF files by
default. A lightweight fixture can be produced from the CSV already present in
this repository with --sample-from-csv.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path


DEFAULT_MODEL = "ACCESS-CM2"
DEFAULT_MEMBER = "r1i1p1f1"
DEFAULT_VARIABLE = "tasmax"
DEFAULT_VERSION = "v2.0"
DEFAULT_SCENARIOS = ("ssp126", "ssp245", "ssp585")
DEFAULT_YEARS = tuple(range(2030, 2101, 5))
MONTHS = ("Jan", "Fev", "Mar", "Avr", "Mai", "Juin", "Juil", "Aout", "Sep", "Oct", "Nov", "Dec")

# Coarse polygons that keep the NEX 0.25 degree grid around metropolitan France
# and Corsica without requiring a shapefile dependency. The browser still uses
# geo.api.gouv.fr commune centroids before choosing the nearest retained point.
MAINLAND_POLYGON = (
    (-5.35, 48.80),
    (-4.90, 47.70),
    (-4.70, 46.10),
    (-2.00, 43.25),
    (1.40, 42.25),
    (3.30, 42.30),
    (4.85, 43.05),
    (7.70, 43.55),
    (7.90, 49.15),
    (6.20, 50.95),
    (2.40, 51.20),
    (-1.70, 50.05),
)

CORSICA_POLYGON = (
    (8.45, 41.30),
    (9.65, 41.30),
    (9.75, 43.10),
    (8.45, 43.10),
)


def parse_years(value: str) -> list[int]:
    if ":" in value:
        parts = [int(p) for p in value.split(":")]
        if len(parts) == 2:
            start, stop = parts
            step = 1
        elif len(parts) == 3:
            start, stop, step = parts
        else:
            raise argparse.ArgumentTypeError("Use START:STOP[:STEP] or comma-separated years")
        if step <= 0:
            raise argparse.ArgumentTypeError("Year step must be positive")
        return list(range(start, stop + 1, step))
    return [int(p.strip()) for p in value.split(",") if p.strip()]


def source_url(model: str, scenario: str, member: str, variable: str, year: int, version: str) -> str:
    suffix = f"_{version}" if version else ""
    filename = f"{variable}_day_{model}_{scenario}_{member}_gn_{year}{suffix}.nc"
    key = f"NEX-GDDP-CMIP6/{model}/{scenario}/{member}/{variable}/{filename}"
    return f"https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com/{key}"


def cache_path(data_dir: Path, model: str, scenario: str, member: str, variable: str, year: int, version: str) -> Path:
    suffix = f"_{version}" if version else ""
    filename = f"{variable}_day_{model}_{scenario}_{member}_gn_{year}{suffix}.nc"
    return data_dir / model / scenario / member / variable / filename


def expected_files(args: argparse.Namespace) -> list[tuple[int, str, Path, str]]:
    files = []
    for year in args.years:
        for scenario in args.scenarios:
            path = cache_path(args.data_dir, args.model, scenario, args.member, args.variable, year, args.version)
            url = source_url(args.model, scenario, args.member, args.variable, year, args.version)
            files.append((year, scenario, path, url))
    return files


def ensure_file(url: str, path: Path, *, allow_download: bool) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    if not allow_download:
        raise FileNotFoundError(f"Missing cached NetCDF: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".part", dir=str(path.parent))
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)
    try:
        with urllib.request.urlopen(url, timeout=120) as response, tmp_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def normalize_lon(lon: float) -> float:
    lon = float(lon)
    return lon - 360.0 if lon > 180.0 else lon


def point_in_poly(lon: float, lat: float, poly: tuple[tuple[float, float], ...]) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def in_france_mvp(lat: float, lon: float) -> bool:
    return point_in_poly(lon, lat, MAINLAND_POLYGON) or point_in_poly(lon, lat, CORSICA_POLYGON)


def point_id(lat: float, lon: float) -> str:
    def tag(value: float) -> str:
        return f"{value:.3f}".replace("-", "m").replace(".", "p")

    return f"g_{tag(lat)}_{tag(lon)}"


def load_netcdf_modules():
    try:
        import numpy as np
        from netCDF4 import Dataset, num2date
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency for the full NetCDF build. Install with:\n"
            "  python3 -m pip install -r pipeline/requirements.txt\n"
            f"Original error: {exc}"
        ) from exc
    return np, Dataset, num2date


def select_grid_points(ds, np) -> list[dict]:
    lats = np.asarray(ds.variables["lat"][:], dtype=float)
    lons_raw = np.asarray(ds.variables["lon"][:], dtype=float)
    points = []
    for lat_idx, lat in enumerate(lats):
        if lat < 41.0 or lat > 52.0:
            continue
        for lon_idx, raw_lon in enumerate(lons_raw):
            lon = normalize_lon(raw_lon)
            if lon < -6.0 or lon > 10.0:
                continue
            if not in_france_mvp(float(lat), float(lon)):
                continue
            points.append(
                {
                    "id": point_id(float(lat), float(lon)),
                    "lat_idx": int(lat_idx),
                    "lon_idx": int(lon_idx),
                    "lat": round(float(lat), 4),
                    "lon": round(float(lon), 4),
                }
            )
    points.sort(key=lambda p: (p["lat"], p["lon"]))
    return points


def contiguous_runs(indices: list[int]) -> list[tuple[int, int]]:
    if not indices:
        return []

    runs = []
    start = prev = indices[0]
    for idx in indices[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        runs.append((start, prev))
        start = prev = idx
    runs.append((start, prev))
    return runs


def month_masks(ds, np, num2date) -> list:
    time_var = ds.variables["time"]
    dates = num2date(
        time_var[:],
        units=time_var.units,
        calendar=getattr(time_var, "calendar", "standard"),
        only_use_cftime_datetimes=False,
        only_use_python_datetimes=False,
    )
    months = np.asarray([d.month for d in dates], dtype=int)
    return [months == month for month in range(1, 13)]


def extract_file(path: Path, grid_points: list[dict] | None) -> tuple[list[dict], dict[str, list[float]]]:
    np, Dataset, num2date = load_netcdf_modules()
    with Dataset(path) as ds:
        if grid_points is None:
            grid_points = select_grid_points(ds, np)
            if not grid_points:
                raise RuntimeError("No grid points selected for France metropolitaine + Corse")

        var = ds.variables["tasmax"]
        masks = month_masks(ds, np, num2date)
        lat_indices = [point["lat_idx"] for point in grid_points]
        lat_start = min(lat_indices)
        lat_end = max(lat_indices)
        lon_runs = contiguous_runs(sorted({point["lon_idx"] for point in grid_points}))

        extracted: dict[str, list[float]] = {}
        valid_grid_points: list[dict] = []
        skipped_points: list[str] = []
        for lon_start, lon_end in lon_runs:
            run_points = [
                point
                for point in grid_points
                if lon_start <= point["lon_idx"] <= lon_end
            ]
            block = np.ma.filled(
                var[:, lat_start : lat_end + 1, lon_start : lon_end + 1],
                np.nan,
            ).astype(float) - 273.15
            for point in run_points:
                lat_offset = point["lat_idx"] - lat_start
                lon_offset = point["lon_idx"] - lon_start
                series = block[:, lat_offset, lon_offset]
                values = []
                valid = True
                for mask in masks:
                    month_values = series[mask]
                    finite_month_values = month_values[np.isfinite(month_values)]
                    if finite_month_values.size == 0:
                        valid = False
                        break
                    val = float(np.max(finite_month_values))
                    if not math.isfinite(val):
                        valid = False
                        break
                    if val < -80.0 or val > 80.0:
                        raise RuntimeError(f"Implausible Celsius value {val:.2f} for {point['id']} in {path}")
                    values.append(round(val, 2))
                if not valid:
                    skipped_points.append(point["id"])
                    continue
                valid_grid_points.append(point)
                extracted[point["id"]] = values

        valid_grid_points.sort(key=lambda p: (p["lat"], p["lon"]))
        if skipped_points:
            preview = ", ".join(skipped_points[:5])
            suffix = "" if len(skipped_points) <= 5 else f", +{len(skipped_points) - 5} more"
            print(f"skipped {len(skipped_points)} masked grid point(s) in {path}: {preview}{suffix}", file=sys.stderr)
        if not valid_grid_points:
            raise RuntimeError(f"No finite grid points found in {path}")
    return valid_grid_points, extracted


def write_json(payload: dict, output: Path, pretty: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        if pretty:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        else:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")


def build_from_netcdf(args: argparse.Namespace) -> dict:
    grid_points = None
    points_by_id: dict[str, dict] = {}
    file_count = 0

    for year, scenario, path, url in expected_files(args):
        print(f"{year} {scenario}: {path}", file=sys.stderr)
        ensure_file(url, path, allow_download=not args.no_download)
        grid_points, values = extract_file(path, grid_points)
        if args.delete_cache_after_read:
            path.unlink(missing_ok=True)
        file_count += 1
        for point in grid_points:
            item = points_by_id.setdefault(
                point["id"],
                {
                    "id": point["id"],
                    "lat": point["lat"],
                    "lon": point["lon"],
                    "values": {},
                },
            )
            year_values = item["values"].setdefault(str(year), {})
            year_values[scenario] = values[point["id"]]

    points = [points_by_id[p["id"]] for p in grid_points or []]
    return {
        "meta": {
            "source": "NASA NEX-GDDP-CMIP6 v2.0",
            "source_url": "https://www.nasa.gov/nex/gddp-cmip6/",
            "model": args.model,
            "member": args.member,
            "variable": args.variable,
            "scenarios": list(args.scenarios),
            "years": list(args.years),
            "unit": "degC",
            "statistic": "monthly maximum of daily tasmax",
            "grid": "0.25 degree NEX-GDDP-CMIP6 grid, nearest point to commune centroid",
            "coverage": "France metropolitaine + Corse, coarse polygon mask",
            "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "files": file_count,
            "points": len(points),
        },
        "points": points,
    }


def build_sample_from_csv(args: argparse.Namespace) -> dict:
    rows = []
    with args.sample_from_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)
    if not rows:
        raise SystemExit(f"No rows in {args.sample_from_csv}")

    lat = round(float(rows[0]["grid_lat"]), 4)
    lon = round(float(rows[0]["grid_lon"]), 4)
    pid = point_id(lat, lon)
    values: dict[str, dict[str, list[float]]] = {str(args.sample_year): {}}

    by_scenario: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in rows:
        by_scenario[row["scenario"]].append((int(row["month"]), float(row["tasmax_c"])))

    for scenario in args.scenarios:
        month_values = sorted(by_scenario.get(scenario, []))
        if len(month_values) != 12:
            raise SystemExit(f"Expected 12 monthly values for {scenario}, got {len(month_values)}")
        values[str(args.sample_year)][scenario] = [round(v, 2) for _, v in month_values]

    return {
        "meta": {
            "source": "NASA NEX-GDDP-CMIP6 v2.0",
            "source_url": "https://www.nasa.gov/nex/gddp-cmip6/",
            "model": args.model,
            "member": args.member,
            "variable": args.variable,
            "scenarios": list(args.scenarios),
            "years": [args.sample_year],
            "unit": "degC",
            "statistic": "monthly maximum of daily tasmax",
            "grid": "0.25 degree NEX-GDDP-CMIP6 grid, nearest point to commune centroid",
            "coverage": "sample fixture from outputs/santa_maria_poggio_2035_tasmax_monthly_max.csv",
            "coverage_note": "Fixture un point : relancer le pipeline complet pour France metropolitaine + Corse.",
            "sample_commune": "Santa-Maria-Poggio",
            "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "points": 1,
        },
        "points": [
            {
                "id": pid,
                "lat": lat,
                "lon": lon,
                "values": values,
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--member", default=DEFAULT_MEMBER)
    parser.add_argument("--variable", default=DEFAULT_VARIABLE)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--scenarios", nargs="+", default=list(DEFAULT_SCENARIOS))
    parser.add_argument("--years", type=parse_years, default=list(DEFAULT_YEARS), help="2030:2100:5 or 2030,2035")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw/nex-gddp-cmip6"))
    parser.add_argument("--output", type=Path, default=Path("docs/climat_france_tasmax.json"))
    parser.add_argument("--no-download", action="store_true", help="Fail if an expected NetCDF is absent from --data-dir")
    parser.add_argument("--check-files", action="store_true", help="Only list expected cached files and report missing files")
    parser.add_argument(
        "--delete-cache-after-read",
        action="store_true",
        help="Delete each cached NetCDF after extraction to reduce disk usage",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON instead of compact output")
    parser.add_argument("--sample-from-csv", type=Path, help="Build a one-point fixture from an existing monthly CSV")
    parser.add_argument("--sample-year", type=int, default=2035)
    args = parser.parse_args()

    if args.check_files:
        missing = []
        for year, scenario, path, _url in expected_files(args):
            ok = path.exists() and path.stat().st_size > 0
            print(f"{'ok' if ok else 'missing'} {year} {scenario} {path}")
            if not ok:
                missing.append(path)
        raise SystemExit(1 if missing else 0)

    if args.sample_from_csv:
        payload = build_sample_from_csv(args)
    else:
        payload = build_from_netcdf(args)

    write_json(payload, args.output, args.pretty)
    print(f"wrote {args.output} ({len(payload['points'])} point(s))")


if __name__ == "__main__":
    main()
