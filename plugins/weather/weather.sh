#!/usr/bin/env bash
# Weather forecast with cloud cover for outdoor activity planning
# Uses Open-Meteo API with auto model selection

set -euo pipefail

# === DEPENDENCY CHECK ===
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed."
    echo "Install with: brew install jq"
    exit 1
fi

if ! command -v curl &> /dev/null; then
    echo "Error: curl is required but not installed."
    exit 1
fi

# === CONFIGURATION ===
# Vienna, Austria (default)
LAT="48.18601"
LON="16.32105"
LOCATION_NAME="Vienna"

# Defaults
FORECAST_DAYS=2
CLOUD_THRESHOLD=30  # "good" window threshold
RAW_OUTPUT=false
MODEL="auto"  # auto, icon_d2, best_match

# === PARSE ARGUMENTS ===
while [[ $# -gt 0 ]]; do
    case $1 in
        --location|-l)
            # Geocode location name to coordinates
            SEARCH="$2"
            GEO_URL="https://geocoding-api.open-meteo.com/v1/search?name=$(echo "$SEARCH" | sed 's/ /%20/g')&count=1"
            GEO_RESULT=$(curl -s "$GEO_URL")

            if ! echo "$GEO_RESULT" | jq -e '.results[0]' > /dev/null 2>&1; then
                echo "Error: Could not find location '$SEARCH'"
                echo "Try a different spelling or use --lat/--lon"
                exit 1
            fi

            LAT=$(echo "$GEO_RESULT" | jq -r '.results[0].latitude')
            LON=$(echo "$GEO_RESULT" | jq -r '.results[0].longitude')
            LOCATION_NAME=$(echo "$GEO_RESULT" | jq -r '.results[0].name + ", " + .results[0].country')
            shift 2
            ;;
        --days) FORECAST_DAYS="$2"; shift 2 ;;
        --threshold) CLOUD_THRESHOLD="$2"; shift 2 ;;
        --raw) RAW_OUTPUT=true; shift ;;
        --lat) LAT="$2"; shift 2 ;;
        --lon) LON="$2"; shift 2 ;;
        --model) MODEL="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: weather.sh [OPTIONS]"
            echo ""
            echo "Location:"
            echo "  --location, -l NAME  Search for location by name (e.g., 'Innsbruck')"
            echo "  --lat N              Override latitude"
            echo "  --lon N              Override longitude"
            echo ""
            echo "Options:"
            echo "  --days N        Forecast days (default: 2, max: 2 for ICON-D2)"
            echo "  --threshold N   Cloud % threshold for 'good' windows (default: 30)"
            echo "  --model MODEL   Weather model: auto, icon_d2, best_match (default: auto)"
            echo "  --raw           Output raw JSON"
            echo ""
            echo "Examples:"
            echo "  weather.sh                          # Vienna forecast"
            echo "  weather.sh -l Innsbruck             # Innsbruck forecast"
            echo "  weather.sh -l 'Chamonix, France'    # Chamonix forecast"
            echo "  weather.sh --threshold 40           # Show <40% cloud windows"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# === MODEL SELECTION ===
# ICON-D2: Best for Central Europe/Alps (2.2km res, 48h)
# Auto-detect if location is within ICON-D2 coverage
select_model() {
    if [[ "$MODEL" != "auto" ]]; then
        echo "$MODEL"
        return
    fi

    # ICON-D2 rough coverage: lat 43-55, lon 2-20
    local lat_ok lon_ok
    lat_ok=$(echo "$LAT" | awk '{print ($1 >= 43 && $1 <= 55) ? 1 : 0}')
    lon_ok=$(echo "$LON" | awk '{print ($1 >= 2 && $1 <= 20) ? 1 : 0}')

    if [[ "$lat_ok" == "1" && "$lon_ok" == "1" ]]; then
        echo "icon_d2"
    else
        echo "best_match"
    fi
}

SELECTED_MODEL=$(select_model)

# Limit days for ICON-D2
if [[ "$SELECTED_MODEL" == "icon_d2" && "$FORECAST_DAYS" -gt 2 ]]; then
    echo "Note: ICON-D2 model limited to 2-day forecast" >&2
    FORECAST_DAYS=2
fi

# === FETCH DATA ===
API_URL="https://api.open-meteo.com/v1/forecast"
PARAMS="latitude=${LAT}&longitude=${LON}"
PARAMS+="&hourly=temperature_2m,apparent_temperature,cloud_cover,precipitation_probability,precipitation,wind_speed_10m,wind_gusts_10m,is_day,weather_code"
PARAMS+="&current=temperature_2m,apparent_temperature,cloud_cover,weather_code,is_day,wind_speed_10m,precipitation"
PARAMS+="&daily=sunrise,sunset,weather_code,precipitation_sum,wind_speed_10m_max"
PARAMS+="&models=${SELECTED_MODEL}"
PARAMS+="&timezone=auto"
PARAMS+="&forecast_days=${FORECAST_DAYS}"
PARAMS+="&wind_speed_unit=kmh"
PARAMS+="&temperature_unit=celsius"
PARAMS+="&precipitation_unit=mm"

DATA=$(curl -s --max-time 10 "${API_URL}?${PARAMS}" 2>/dev/null) || {
    echo "Error: Failed to connect to Open-Meteo API"
    echo "Check your internet connection"
    exit 1
}

# === RAW OUTPUT MODE ===
if $RAW_OUTPUT; then
    echo "$DATA" | jq .
    exit 0
fi

# === CHECK FOR ERRORS ===
if echo "$DATA" | jq -e '.error' > /dev/null 2>&1; then
    echo "Error from API:"
    echo "$DATA" | jq -r '.reason // .error'
    exit 1
fi

# === WEATHER CODE TO DESCRIPTION ===
weather_desc() {
    local code=$1
    case $code in
        0) echo "Clear sky" ;;
        1) echo "Mainly clear" ;;
        2) echo "Partly cloudy" ;;
        3) echo "Overcast" ;;
        45|48) echo "Foggy" ;;
        51|53|55) echo "Drizzle" ;;
        61|63|65) echo "Rain" ;;
        66|67) echo "Freezing rain" ;;
        71|73|75) echo "Snow" ;;
        77) echo "Snow grains" ;;
        80|81|82) echo "Rain showers" ;;
        85|86) echo "Snow showers" ;;
        95) echo "Thunderstorm" ;;
        96|99) echo "Thunderstorm + hail" ;;
        *) echo "Unknown" ;;
    esac
}

# === EXTRACT CURRENT CONDITIONS ===
CURRENT_TEMP=$(echo "$DATA" | jq -r '.current.temperature_2m')
CURRENT_FEELS=$(echo "$DATA" | jq -r '.current.apparent_temperature')
CURRENT_CLOUD=$(echo "$DATA" | jq -r '.current.cloud_cover')
CURRENT_WIND=$(echo "$DATA" | jq -r '.current.wind_speed_10m')
CURRENT_PRECIP=$(echo "$DATA" | jq -r '.current.precipitation')
CURRENT_CODE=$(echo "$DATA" | jq -r '.current.weather_code')
CURRENT_DESC=$(weather_desc "$CURRENT_CODE")

SUNRISE=$(echo "$DATA" | jq -r '.daily.sunrise[0]' | cut -dT -f2 | cut -c1-5)
SUNSET=$(echo "$DATA" | jq -r '.daily.sunset[0]' | cut -dT -f2 | cut -c1-5)

# === MODEL DISPLAY NAME ===
MODEL_DISPLAY="ICON-D2"
[[ "$SELECTED_MODEL" == "best_match" ]] && MODEL_DISPLAY="Best Match"

# === HEADER ===
echo ""
echo "Weather for ${LOCATION_NAME} (${LAT}°N, ${LON}°E) - ${MODEL_DISPLAY}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
printf "Now: %.0f°C (feels %.0f°C), %.0f%% clouds, %.0f km/h wind" "$CURRENT_TEMP" "$CURRENT_FEELS" "$CURRENT_CLOUD" "$CURRENT_WIND"
if (( $(echo "$CURRENT_PRECIP > 0" | bc -l) )); then
    printf ", %.1fmm precip" "$CURRENT_PRECIP"
fi
echo ""
echo "Conditions: ${CURRENT_DESC}"
echo "Sunrise: ${SUNRISE}  Sunset: ${SUNSET}"

# === PROCESS HOURLY DATA WITH JQ ===
echo "$DATA" | jq -r --arg threshold "$CLOUD_THRESHOLD" '
  # Helper to create cloud bar
  def cloud_bar:
    . as $pct |
    (20 - ($pct / 5 | floor)) as $filled |
    (20 - $filled) as $empty |
    ("█" * $filled) + ("░" * $empty);

  # Format wind with color indicator
  def wind_indicator:
    if . >= 40 then "💨"
    elif . >= 25 then "🌬️"
    else ""
    end;

  # Combine hourly arrays into objects
  [.hourly.time, .hourly.cloud_cover, .hourly.temperature_2m, .hourly.is_day, .hourly.wind_speed_10m, .hourly.precipitation_probability, .hourly.precipitation]
  | transpose
  | map({
      datetime: .[0],
      date: .[0][0:10],
      hour: .[0][11:16],
      cloud: (.[1] | floor),
      temp: .[2],
      is_day: .[3],
      wind: (.[4] | floor),
      precip_prob: (.[5] // 0 | floor),
      precip: (.[6] // 0)
    })
  | group_by(.date)
  | .[]
  | . as $day_data
  | "\n📅 \($day_data[0].date):",
    "  Time  Cloud                         Temp   Wind  Rain%",
    ($day_data
     | map(select(.is_day == 1))
     | .[]
     | "  \(.hour) \(.cloud | tostring | if length == 1 then "  \(.)" elif length == 2 then " \(.)" else . end)% \(.cloud | cloud_bar) \(.temp | floor | tostring | if length == 1 then "  \(.)" elif length == 2 then " \(.)" else . end)°C  \(.wind | tostring | if length == 1 then " \(.)" else . end)km/h \(.precip_prob | tostring | if length == 1 then "  \(.)" elif length == 2 then " \(.)" else . end)%\(if .cloud < ($threshold | tonumber) and .precip_prob < 20 then " ✓" else "" end)"
    ),
    # Summary for the day
    ($day_data
     | map(select(.is_day == 1))
     | if length > 0 then
         # Find consecutive good windows (low cloud AND low rain probability)
         reduce .[] as $h (
           {windows: [], current: null};
           if ($h.cloud < ($threshold | tonumber)) and ($h.precip_prob < 20) then
             if .current == null then
               .current = {start: $h.hour, end: $h.hour, clouds: [$h.cloud], temps: [$h.temp], winds: [$h.wind]}
             else
               .current.end = $h.hour | .current.clouds += [$h.cloud] | .current.temps += [$h.temp] | .current.winds += [$h.wind]
             end
           else
             if .current != null then
               .windows += [.current] | .current = null
             else
               .
             end
           end
         )
         | if .current != null then .windows += [.current] else . end
         | .windows
         | if length > 0 then
             "\nBest outdoor windows:",
             (.[] | "  ✓ \(.start)-\(.end)  \((.clouds | add / length | floor))% clouds, \((.temps | min | floor))-\((.temps | max | floor))°C, \((.winds | max))km/h max wind")
           else
             "\n⚠️  No ideal windows (clouds <\($threshold)% + rain <20%)"
           end
       else
         empty
       end
    )
'

echo ""
