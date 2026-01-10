---
name: skitour
description: Ski touring conditions for Austrian Alps - avalanche danger, snow depth, and weather forecast combined.
allowed-tools: [Bash, Read]
user-invocable: true
---

# Ski Touring Conditions

Get combined avalanche, snow, and weather data for ski touring in the Austrian Alps.

## Prerequisites

- **bash 4.0+** (for associative arrays)
  - macOS ships with bash 3.x: `brew install bash`
  - Linux: Usually pre-installed
- **uv** (for coordinate lookup feature)
  - `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **jq, curl, bc** (checked at runtime)

## When to Invoke

- User asks about ski touring / backcountry skiing conditions
- User wants avalanche danger levels for a specific area
- Phrases like "skitour", "Lawinengefahr", "snow conditions", "touring conditions"
- User mentions Austrian touring areas (Stubai, Rax, Hochschwab, Lech, etc.)

## Quick Usage

```bash
# Single location by name
./skitour.sh --location stubai
./skitour.sh --location rax

# Single location by coordinates (auto-detects region)
./skitour.sh --lat 47.1 --lon 11.3

# Compare multiple locations
./skitour.sh --compare "stubai,rax,lech"
```

## Available Locations

| Region | Locations |
|--------|-----------|
| **Tyrol (AT-07)** | stubai, obergurgl, soelden, mayrhofen, hintertux, kuehtai, stanton, galtuer, kaunertal, seefeld, kitzbuehel |
| **Carinthia (AT-02)** | heiligenblut, badkleinkirchheim, mallnitz |
| **Vorarlberg (AT-08)** | lech, gargellen, kleinwalsertal, brand |
| **Lower Austria (AT-03)** | rax, schneeberg, otscher, durrenstein |
| **Styria (AT-06)** | hochschwab, schneealpe, veitsch, stuhleck |

## Data Sources

| Data | Source | Coverage | Freshness |
|------|--------|----------|-----------|
| Avalanche danger | lawinen-warnung.eu / avalanche.report | All Austrian alpine regions | Updated daily ~17:00 |
| Snow depth | GeoSphere SNOWGRID | Austria, 1km grid | 1 day behind |
| Weather | Open-Meteo ICON-D2 | Alps/Europe, 2.2km | 48h forecast |

## Example Output

```
═══════════════════════════════════════════════════════════════
  📍 STUBAI (Stubaier Alpen Mitte)
     Coordinates: 47.111°N, 11.308°E
═══════════════════════════════════════════════════════════════

🔺 AVALANCHE DANGER
─────────────────────────────────────────────────────────────────
   Danger level: 2 - Moderate
   Trend: increasing
   Main problem: wind_slab
   Valid until: 2026-01-10

❄️  SNOW DEPTH
─────────────────────────────────────────────────────────────────
   Current: 45 cm (SNOWGRID, 1 day behind)

🌤️  WEATHER FORECAST
─────────────────────────────────────────────────────────────────
   Hour  Temp   Wind    Cloud  Precip%
   06:00  -6.2°C     2km/h   77%     0%
   07:00  -6.3°C     5km/h   97%     0%
   08:00  -5.7°C     5km/h  100%     0%
   ...
```

## Limitations

- Snow depth data is 1 day behind (GeoSphere processing delay)
- Avalanche bulletins update daily around 17:00, may be outdated in morning
- Weather forecast limited to 48 hours (ICON-D2 range)
- Salzburg (AT-05) not yet supported (data source issue)
