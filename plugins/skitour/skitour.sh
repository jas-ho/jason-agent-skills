#!/usr/bin/env bash
# Ski touring conditions: avalanche danger, snow depth, weather
# Data sources: lawinen-warnung.eu, GeoSphere SNOWGRID, Open-Meteo ICON-D2

set -euo pipefail

# === Dependency Check ===
for cmd in jq curl bc; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Error: $cmd is required but not installed." >&2
        exit 1
    fi
done

# === Configuration ===

# Known touring locations with coordinates and region mappings
declare -A LOCATIONS=(
    ["rax"]="47.706,15.733,AT-03,AT-03-04"
    ["schneeberg"]="47.767,15.807,AT-03,AT-03-04"
    ["hochschwab"]="47.617,15.133,AT-06,AT-06-10"
    ["schneealpe"]="47.683,15.583,AT-06,AT-06-11"
    ["veitsch"]="47.617,15.517,AT-06,AT-06-11"
    ["otscher"]="47.867,15.200,AT-03,AT-03-01"
    ["durrenstein"]="47.850,15.050,AT-03,AT-03-01"
    ["stuhleck"]="47.583,15.767,AT-06,AT-06-11"
)

# EAWS micro-region names (for display)
declare -A REGION_NAMES=(
    ["AT-03-01"]="Ybbstaler Alpen"
    ["AT-03-04"]="Rax - Schneeberggebiet"
    ["AT-03-06"]="Gippel - Göllergebiet"
    ["AT-06-09"]="Eisenerzer Alpen"
    ["AT-06-10"]="Hochschwab"
    ["AT-06-11"]="Mürzsteger Alpen"
)

# === Helper Functions ===
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Get ski touring conditions (avalanche, snow, weather) for Austrian Alps.

Options:
    -l, --location NAME     Location name (rax, schneeberg, hochschwab, etc.)
    --lat LAT               Latitude (decimal degrees)
    --lon LON               Longitude (decimal degrees)
    -c, --compare LIST      Compare locations (comma-separated)
    -h, --help              Show this help

Examples:
    $(basename "$0") --location rax
    $(basename "$0") --lat 47.617 --lon 15.133
    $(basename "$0") --compare "rax,hochschwab,schneealpe"

Available locations: ${!LOCATIONS[*]}
EOF
    exit 0
}

# Get avalanche bulletin from lawinen-warnung.eu
get_avalanche_data() {
    local region_code="$1"  # e.g., AT-03
    local micro_region="$2"  # e.g., AT-03-04

    local url="https://static.lawinen-warnung.eu/bulletins/latest/${region_code}.json"
    local response

    if ! response=$(curl -sf --max-time 10 "$url" 2>/dev/null); then
        echo "ERROR: Failed to fetch avalanche data for $region_code"
        return 1
    fi

    # Extract danger rating for the specific micro-region
    # Structure: array of bulletins, each with .regions (array of ID strings)
    # Use first() to get only the first matching bulletin
    echo "$response" | jq -r --arg mr "$micro_region" '
        first(.[] | select(.regions | index($mr))) |
        {
            dangerAbove: .forenoon.dangerRatingAbove,
            dangerBelow: .forenoon.dangerRatingBelow,
            treeline: .forenoon.treeline,
            trend: .tendency,
            problem: .forenoon.avalancheProblem1.avalancheProblem,
            validUntil: .validity.until
        }
    ' 2>/dev/null || echo '{"dangerAbove": "unavailable"}'
}

# Get snow depth from GeoSphere SNOWGRID
get_snow_depth() {
    local lat="$1"
    local lon="$2"

    # SNOWGRID data is 1 day behind, so query yesterday
    local yesterday
    yesterday=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)
    local today
    today=$(date +%Y-%m-%d)

    local url="https://dataset.api.hub.geosphere.at/v1/timeseries/historical/snowgrid_cl-v2-1d-1km"
    url+="?parameters=snow_depth&lat_lon=${lat},${lon}&start=${yesterday}&end=${today}&output_format=csv"

    local response
    if ! response=$(curl -sf --max-time 10 "$url" 2>/dev/null); then
        echo "ERROR: Failed to fetch snow depth"
        return 1
    fi

    # Parse CSV - get the last snow_depth value
    local depth
    depth=$(echo "$response" | tail -1 | cut -d',' -f2 | tr -d ' ')

    if [[ -z "$depth" || "$depth" == "snow_depth" ]]; then
        echo "0"
    else
        # Convert from meters to cm
        printf "%.0f" "$(echo "$depth * 100" | bc -l 2>/dev/null || echo "0")"
    fi
}

# Get weather forecast from Open-Meteo ICON-D2
get_weather() {
    local lat="$1"
    local lon="$2"

    local url="https://api.open-meteo.com/v1/dwd-icon"
    url+="?latitude=${lat}&longitude=${lon}"
    url+="&hourly=temperature_2m,windspeed_10m,winddirection_10m,precipitation_probability,cloudcover"
    url+="&models=icon_d2"
    url+="&forecast_days=2"
    url+="&timezone=Europe/Vienna"

    curl -sf --max-time 10 "$url" 2>/dev/null || echo '{"error": "fetch failed"}'
}

# Format danger level (handles both text and numeric)
format_danger() {
    local level="$1"
    case "${level,,}" in
        1|low) echo "1 - Low" ;;
        2|moderate) echo "2 - Moderate" ;;
        3|considerable) echo "3 - Considerable" ;;
        4|high) echo "4 - High" ;;
        5|"very high"|"very_high") echo "5 - Very High" ;;
        *) echo "$level" ;;
    esac
}

# Main output for a single location
show_location() {
    local name="$1"
    local lat="$2"
    local lon="$3"
    local region_code="$4"
    local micro_region="$5"

    echo "═══════════════════════════════════════════════════════════════"
    echo "  📍 ${name^^} (${REGION_NAMES[$micro_region]:-$micro_region})"
    echo "     Coordinates: ${lat}°N, ${lon}°E"
    echo "═══════════════════════════════════════════════════════════════"
    echo

    # Avalanche data
    echo "🔺 AVALANCHE DANGER"
    echo "─────────────────────────────────────────────────────────────────"
    local avy_data
    avy_data=$(get_avalanche_data "$region_code" "$micro_region")

    if [[ "$avy_data" != *"ERROR"* && "$avy_data" != *"unavailable"* ]]; then
        local danger_above danger_below treeline trend problem valid
        danger_above=$(echo "$avy_data" | jq -r '.dangerAbove // "unknown"')
        danger_below=$(echo "$avy_data" | jq -r '.dangerBelow // "unknown"')
        treeline=$(echo "$avy_data" | jq -r '.treeline // false')
        trend=$(echo "$avy_data" | jq -r '.trend // "unknown"')
        problem=$(echo "$avy_data" | jq -r '.problem // "none"')
        valid=$(echo "$avy_data" | jq -r '.validUntil // ""' | cut -dT -f1)

        if [[ "$treeline" == "true" ]]; then
            echo "   Above treeline: $(format_danger "$danger_above")"
            echo "   Below treeline: $(format_danger "$danger_below")"
        else
            echo "   Danger level: $(format_danger "$danger_above")"
        fi
        echo "   Trend: $trend"
        [[ "$problem" != "none" && "$problem" != "null" && -n "$problem" ]] && echo "   Main problem: $problem"
        [[ -n "$valid" ]] && echo "   Valid until: $valid"
    else
        echo "   Avalanche data unavailable"
    fi
    echo

    # Snow depth
    echo "❄️  SNOW DEPTH"
    echo "─────────────────────────────────────────────────────────────────"
    local snow_cm
    snow_cm=$(get_snow_depth "$lat" "$lon")
    echo "   Current: ${snow_cm} cm (SNOWGRID, 1 day behind)"
    echo

    # Weather
    echo "🌤️  WEATHER FORECAST"
    echo "─────────────────────────────────────────────────────────────────"
    local weather_json
    weather_json=$(get_weather "$lat" "$lon")

    if [[ "$weather_json" != *"error"* ]]; then
        # Show next 12 hours in compact format (single jq call instead of 60)
        echo "   Hour  Temp   Wind    Cloud  Precip%"
        echo "$weather_json" | jq -r '
            . as $root |
            range(12) |
            . as $i |
            ($root.hourly.time[$i] // empty) as $time |
            if $time then
                ($time | split("T")[1] | split(":")[0] | ltrimstr("0") | if . == "" then "0" else . end) as $hour |
                ($root.hourly.temperature_2m[$i] // 0) as $temp |
                ($root.hourly.windspeed_10m[$i] // 0) as $wind |
                ($root.hourly.cloudcover[$i] // 0) as $cloud |
                ($root.hourly.precipitation_probability[$i] // 0) as $precip |
                "\($hour)\t\($temp)\t\($wind)\t\($cloud)\t\($precip)"
            else empty end
        ' | while IFS=$'\t' read -r hour temp wind cloud precip; do
            printf "   %02d:00 %5.1f°C %5.0fkm/h %4.0f%%   %3.0f%%\n" \
                "$hour" "$temp" "$wind" "$cloud" "$precip"
        done
    else
        echo "   Weather data unavailable"
    fi
    echo
}

# === Main ===
main() {
    local location="" lat="" lon="" compare=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -l|--location) location="${2,,}"; shift 2 ;;
            --lat) lat="$2"; shift 2 ;;
            --lon) lon="$2"; shift 2 ;;
            -c|--compare) compare="$2"; shift 2 ;;
            -h|--help) usage ;;
            *) echo "Unknown option: $1" >&2; exit 1 ;;
        esac
    done

    # Handle compare mode
    if [[ -n "$compare" ]]; then
        IFS=',' read -ra locs <<< "$compare"
        for loc in "${locs[@]}"; do
            loc="${loc,,}"  # lowercase
            loc="${loc// /}"  # remove spaces
            if [[ -v "LOCATIONS[$loc]" ]]; then
                IFS=',' read -r lat lon region micro <<< "${LOCATIONS[$loc]}"
                show_location "$loc" "$lat" "$lon" "$region" "$micro"
            else
                echo "Unknown location: $loc"
                echo "Available: ${!LOCATIONS[*]}"
            fi
        done
        exit 0
    fi

    # Single location mode
    if [[ -n "$location" ]]; then
        if [[ -v "LOCATIONS[$location]" ]]; then
            IFS=',' read -r lat lon region micro <<< "${LOCATIONS[$location]}"
            show_location "$location" "$lat" "$lon" "$region" "$micro"
        else
            echo "Unknown location: $location"
            echo "Available: ${!LOCATIONS[*]}"
            exit 1
        fi
    elif [[ -n "$lat" && -n "$lon" ]]; then
        # TODO: Implement coordinate → region lookup using EAWS polygons
        echo "Coordinate lookup not yet implemented."
        echo "Use --location with a known location: ${!LOCATIONS[*]}"
        exit 1
    else
        usage
    fi
}

main "$@"
