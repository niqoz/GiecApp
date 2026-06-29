#!/usr/bin/env python3
import argparse
import calendar
import os
import textwrap
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import numpy as np
import pandas as pd
import requests
import seaborn as sns
from matplotlib import pyplot as plt
from netCDF4 import Dataset, num2date


TOKENS = {
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "axis": "#D7DBE7",
}

PALETTE = {
    "ssp126": "#A3BEFA",
    "ssp245": "#F0986E",
    "ssp585": "#F390CA",
}

MONTH_LABELS = ["Jan", "Fev", "Mar", "Avr", "Mai", "Juin", "Juil", "Aout", "Sep", "Oct", "Nov", "Dec"]


def add_chart_header(fig, ax, title, subtitle, *, title_width=82, subtitle_width=112):
    title = textwrap.fill(title.strip(), width=title_width, break_long_words=False)
    subtitle = textwrap.fill(subtitle.strip(), width=subtitle_width, break_long_words=False)
    ax.set_title("")
    fig.subplots_adjust(top=0.82)
    left = ax.get_position().x0
    fig.text(left, 0.94, title, ha="left", va="top", fontsize=16, fontweight=700, color=TOKENS["ink"])
    fig.text(left, 0.895, subtitle, ha="left", va="top", fontsize=10.5, color=TOKENS["muted"])


def geocode_commune(name):
    params = {
        "nom": name,
        "fields": "nom,code,centre,departement,region",
        "format": "json",
        "geometry": "centre",
    }
    response = requests.get("https://geo.api.gouv.fr/communes", params=params, timeout=30)
    response.raise_for_status()
    matches = response.json()
    if not matches:
        raise ValueError(f"No French commune found for {name!r}")
    match = matches[0]
    lon, lat = match["centre"]["coordinates"]
    return {
        "name": match["nom"],
        "code": match["code"],
        "department": match["departement"]["nom"],
        "region": match["region"]["nom"],
        "lat": float(lat),
        "lon": float(lon),
    }


def source_url(model, scenario, member, variable, year, version):
    suffix = f"_{version}" if version else ""
    filename = f"{variable}_day_{model}_{scenario}_{member}_gn_{year}{suffix}.nc"
    key = f"NEX-GDDP-CMIP6/{model}/{scenario}/{member}/{variable}/{filename}"
    return f"https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com/{key}"


def ensure_file(url, path):
    if path.exists() and path.stat().st_size > 0:
        return
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        tmp_path = path.with_suffix(path.suffix + ".part")
        with tmp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        tmp_path.replace(path)


def nearest_index(values, target):
    values = np.asarray(values)
    return int(np.abs(values - target).argmin())


def extract_monthly_max(path, scenario, target_lat, target_lon):
    with Dataset(path) as ds:
        lats = ds.variables["lat"][:]
        lons = ds.variables["lon"][:]
        lon_0360 = target_lon % 360
        lat_idx = nearest_index(lats, target_lat)
        lon_idx = nearest_index(lons, lon_0360)

        tasmax_k = np.ma.filled(ds.variables["tasmax"][:, lat_idx, lon_idx], np.nan).astype(float)
        tasmax_c = tasmax_k - 273.15

        time_var = ds.variables["time"]
        dates = num2date(
            time_var[:],
            units=time_var.units,
            calendar=getattr(time_var, "calendar", "standard"),
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=True,
        )

        rows = []
        for month in range(1, 13):
            month_values = [tasmax_c[i] for i, date in enumerate(dates) if date.month == month]
            rows.append(
                {
                    "scenario": scenario,
                    "month": month,
                    "month_label": MONTH_LABELS[month - 1],
                    "tasmax_c": float(np.nanmax(month_values)),
                    "grid_lat": float(lats[lat_idx]),
                    "grid_lon": float(lons[lon_idx]),
                }
            )
        return rows


def build_chart(df, commune, year, model, member, output_png, output_svg):
    sns.set_theme(style="whitegrid", font="DejaVu Sans")
    plt.rcParams.update(
        {
            "figure.facecolor": TOKENS["surface"],
            "axes.facecolor": TOKENS["panel"],
            "axes.edgecolor": TOKENS["axis"],
            "axes.labelcolor": TOKENS["ink"],
            "xtick.color": TOKENS["muted"],
            "ytick.color": TOKENS["muted"],
            "grid.color": TOKENS["grid"],
            "grid.linewidth": 0.8,
        }
    )

    fig, ax = plt.subplots(figsize=(12, 6.8), dpi=160)
    sns.barplot(
        data=df,
        x="month_label",
        y="tasmax_c",
        hue="scenario",
        order=MONTH_LABELS,
        hue_order=list(PALETTE),
        palette=PALETTE,
        edgecolor=TOKENS["ink"],
        linewidth=0.45,
        ax=ax,
    )

    ax.set_xlabel("Mois", labelpad=10)
    ax.set_ylabel("Temperature maximale du jour le plus chaud (degC)", labelpad=10)
    ax.yaxis.grid(True)
    ax.xaxis.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(TOKENS["axis"])
    ax.spines["bottom"].set_color(TOKENS["axis"])

    ymax = float(df["tasmax_c"].max())
    ax.set_ylim(0, max(45, ymax + 4))

    for container in ax.containers:
        labels = [f"{bar.get_height():.1f}" if bar.get_height() >= ymax - 1.5 else "" for bar in container]
        ax.bar_label(container, labels=labels, padding=3, fontsize=8, color=TOKENS["muted"])

    legend = ax.legend(
        title="Scenario",
        ncols=3,
        frameon=False,
        loc="upper left",
        bbox_to_anchor=(0, 1.08),
        borderaxespad=0,
    )
    legend.get_title().set_color(TOKENS["muted"])

    grid_lat = df["grid_lat"].iloc[0]
    grid_lon = df["grid_lon"].iloc[0]
    add_chart_header(
        fig,
        ax,
        f"Santa-Maria-Poggio, {year}: maximum journalier de tasmax par mois",
        (
            "NASA NEX-GDDP-CMIP6 v2.0, modele "
            f"{model}, membre {member}; point de grille le plus proche "
            f"({grid_lat:.3f}N, {grid_lon:.3f}E). Valeurs en degC."
        ),
    )

    fig.text(
        ax.get_position().x0,
        0.04,
        "Lecture: chaque barre est le maximum mensuel des temperatures maximales journalieres simulees.",
        ha="left",
        va="bottom",
        fontsize=9,
        color=TOKENS["muted"],
    )
    fig.tight_layout(rect=[0, 0.06, 1, 0.84])
    fig.savefig(output_png, bbox_inches="tight", facecolor=fig.get_facecolor())
    fig.savefig(output_svg, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commune", default="Santa-Maria-Poggio")
    parser.add_argument("--year", type=int, default=2035)
    parser.add_argument("--model", default="ACCESS-CM2")
    parser.add_argument("--member", default="r1i1p1f1")
    parser.add_argument("--variable", default="tasmax")
    parser.add_argument("--version", default="v2.0")
    parser.add_argument("--scenarios", nargs="+", default=["ssp126", "ssp245", "ssp585"])
    parser.add_argument("--data-dir", default="/tmp")
    parser.add_argument("--output-dir", default="outputs")
    args = parser.parse_args()

    commune = geocode_commune(args.commune)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for scenario in args.scenarios:
        filename = f"{args.variable}_{args.model}_{scenario}_{args.year}_{args.version}.nc"
        path = data_dir / filename
        url = source_url(args.model, scenario, args.member, args.variable, args.year, args.version)
        ensure_file(url, path)
        rows.extend(extract_monthly_max(path, scenario, commune["lat"], commune["lon"]))

    df = pd.DataFrame(rows)
    slug = commune["name"].lower().replace("-", "_").replace(" ", "_")
    csv_path = output_dir / f"{slug}_{args.year}_tasmax_monthly_max.csv"
    png_path = output_dir / f"{slug}_{args.year}_tasmax_monthly_max.png"
    svg_path = output_dir / f"{slug}_{args.year}_tasmax_monthly_max.svg"
    df.to_csv(csv_path, index=False)
    build_chart(df, commune, args.year, args.model, args.member, png_path, svg_path)

    print(f"commune={commune['name']} code={commune['code']} lat={commune['lat']} lon={commune['lon']}")
    print(f"grid_lat={df['grid_lat'].iloc[0]} grid_lon={df['grid_lon'].iloc[0]}")
    print(f"csv={csv_path}")
    print(f"png={png_path}")
    print(f"svg={svg_path}")


if __name__ == "__main__":
    main()
