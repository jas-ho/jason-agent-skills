---
name: skitour
description: Ski touring conditions for Austrian Alps - avalanche danger, snow depth, and weather forecast combined.
allowed-tools: [Bash, Read]
user-invocable: true
---

# Ski Touring Conditions

Get combined avalanche, snow, and weather data for ski touring in the Austrian Alps.

## When to Invoke

- User asks about ski touring / backcountry skiing conditions
- User wants avalanche danger levels for a specific area
- Phrases like "skitour", "Lawinengefahr", "snow conditions", "touring conditions"
- User mentions specific Austrian touring areas (Rax, Schneeberg, Hochschwab, etc.)

## Quick Usage

```bash
# Single location (coordinates or name)
./skitour.sh --location "Rax"
./skitour.sh --lat 47.7 --lon 15.7

# Compare multiple locations
./skitour.sh --compare "Rax,Hochschwab,Schneealpe"

# Specific date (default: today + tomorrow)
./skitour.sh --location "Hochschwab" --date 2026-01-12
```

## Data Sources

| Data | Source | Coverage | Freshness |
|------|--------|----------|-----------|
| Avalanche danger | lawinen-warnung.eu | Austrian regions (AT-03, AT-06, etc.) | Updated daily ~17:00 |
| Snow depth | GeoSphere SNOWGRID | Austria, 1km grid | 1 day behind |
| Weather | Open-Meteo ICON-D2 | Alps/Europe, 2.2km | 48h forecast |

## Austrian Avalanche Regions

The script maps coordinates to EAWS micro-regions for accurate danger ratings:

- **AT-03** (Lower Austria): Rax-Schneeberggebiet (AT-03-04), Ybbstaler Alpen (AT-03-01), etc.
- **AT-06** (Styria): Hochschwab (AT-06-10), Eisenerzer Alpen (AT-06-09), Mürzsteger Alpen (AT-06-11), etc.

## Output

Displays for each location:
1. **Avalanche danger** - Level (1-5), trend, problem types, elevation bands
2. **Snow depth** - Current depth in cm (SNOWGRID measurement)
3. **Weather** - Temperature, wind, precipitation, cloud cover for touring window

## Limitations

- Snow depth data is 1 day behind (GeoSphere processing delay)
- Avalanche bulletins update daily around 17:00, may be outdated in morning
- Weather forecast limited to 48 hours (ICON-D2 range)
- Coordinate → subregion mapping requires EAWS polygon data
