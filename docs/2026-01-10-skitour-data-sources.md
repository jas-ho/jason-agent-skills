# Ski Touring Data Sources Investigation

**Date**: 2026-01-10
**Status**: Working implementation exists in `plugins/skitour/skitour.sh`

## Avalanche Data

**Source**: lawinen-warnung.eu (EAWS/Albina network)

```bash
curl -s "https://static.lawinen-warnung.eu/bulletins/latest/AT-03.json"
```

- **Regions**: AT-03 (Lower Austria), AT-06 (Styria), etc.
- **Update**: Daily ~17:00
- **Structure**: Array of bulletins, each with `.regions` (array of micro-region ID strings)
- **jq pattern**: `first(.[] | select(.regions | index("AT-03-04")))`

**Failed alternatives**:

- `avalanche.report/api` - Returns HTML (JavaScript SPA)
- `lawinen.report` - Only covers Tirol/Südtirol/Trentino

## Snow Depth (GeoSphere SNOWGRID)

```bash
URL="https://dataset.api.hub.geosphere.at/v1/timeseries/historical/snowgrid_cl-v2-1d-1km"
PARAMS="parameters=snow_depth&lat_lon=47.7,15.8&start=2026-01-09&end=2026-01-10&output_format=csv"
```

- **Resolution**: 1km grid
- **Unit**: Meters (multiply by 100 for cm)
- **Lag**: 1 day behind (query yesterday's date)
- **Coverage**: Austria

## Weather (Open-Meteo ICON-D2)

```bash
curl "https://api.open-meteo.com/v1/dwd-icon?latitude=47.7&longitude=15.8&hourly=temperature_2m,windspeed_10m,precipitation_probability,cloudcover&models=icon_d2&forecast_days=2&timezone=Europe/Vienna"
```

- **Resolution**: 2.2km
- **Forecast**: 48 hours
- **Update**: Every 3 hours
- **Best for**: Alps/Central Europe (lat 43-55, lon 2-20)

## EAWS Micro-Regions

| Code | Name |
|------|------|
| AT-03-01 | Ybbstaler Alpen |
| AT-03-04 | Rax - Schneeberggebiet |
| AT-06-10 | Hochschwab |
| AT-06-11 | Mürzsteger Alpen |

Full mapping in `skitour.sh` lines 11-30.
