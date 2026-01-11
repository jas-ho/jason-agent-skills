#!/usr/bin/env bash
# Ski touring conditions: avalanche danger, snow depth, weather
# Data sources: lawinen-warnung.eu, GeoSphere SNOWGRID, Open-Meteo ICON-D2

set -euo pipefail

# === Bash Version Check ===
# Associative arrays require bash 4.0+
if ((BASH_VERSINFO[0] < 4)); then
    echo "Error: bash 4.0+ required (found $BASH_VERSION)" >&2
    echo "On macOS: brew install bash" >&2
    exit 1
fi

# === Dependency Check ===
for cmd in jq curl bc; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Error: $cmd is required but not installed." >&2
        exit 1
    fi
done

# === Configuration ===

# Known touring locations with coordinates and region mappings
# Format: "lat,lon,region_code,micro_region"
declare -A LOCATIONS=(
    # === Lower Austria (AT-03) ===
    ["rax"]="47.706,15.733,AT-03,AT-03-04"
    ["schneeberg"]="47.767,15.807,AT-03,AT-03-04"
    ["otscher"]="47.867,15.200,AT-03,AT-03-01"
    ["durrenstein"]="47.850,15.050,AT-03,AT-03-01"

    # === Styria (AT-06) ===
    ["hochschwab"]="47.617,15.133,AT-06,AT-06-10"
    ["schneealpe"]="47.683,15.583,AT-06,AT-06-11"
    ["veitsch"]="47.617,15.517,AT-06,AT-06-11"
    ["stuhleck"]="47.583,15.767,AT-06,AT-06-11"

    # === Tyrol (AT-07) ===
    ["stubai"]="47.111,11.308,AT-07,AT-07-22"
    ["obergurgl"]="46.871,11.028,AT-07,AT-07-21"
    ["soelden"]="46.967,11.007,AT-07,AT-07-20"
    ["mayrhofen"]="47.167,11.864,AT-07,AT-07-23-01"
    ["hintertux"]="47.115,11.682,AT-07,AT-07-15"
    ["kuehtai"]="47.214,11.023,AT-07,AT-07-14-02"
    ["stanton"]="47.129,10.266,AT-07,AT-07-10"
    ["galtuer"]="46.968,10.187,AT-07,AT-07-12"
    ["kaunertal"]="47.028,10.745,AT-07,AT-07-14-01"
    ["seefeld"]="47.329,11.187,AT-07,AT-07-04-01"
    ["kitzbuehel"]="47.446,12.391,AT-07,AT-07-17-01"

    # === Carinthia (AT-02) ===
    ["heiligenblut"]="47.039,12.841,AT-02,AT-02-01-01"
    ["badkleinkirchheim"]="46.814,13.798,AT-02,AT-02-04-01"
    ["mallnitz"]="46.989,13.171,AT-02,AT-02-03-01-01"

    # === Vorarlberg (AT-08) ===
    ["lech"]="47.209,10.140,AT-08,AT-08-05-01"
    ["gargellen"]="46.972,9.919,AT-08,AT-08-04"
    ["kleinwalsertal"]="47.332,10.139,AT-08,AT-08-03-01"
    ["brand"]="47.104,9.738,AT-08,AT-08-06"
)

# EAWS micro-region names (for display)
declare -A REGION_NAMES=(
    # Lower Austria (AT-03)
    ["AT-03-01"]="Ybbstaler Alpen"
    ["AT-03-04"]="Rax - Schneeberggebiet"
    ["AT-03-06"]="Gippel - Göllergebiet"

    # Styria (AT-06)
    ["AT-06-09"]="Eisenerzer Alpen"
    ["AT-06-10"]="Hochschwab"
    ["AT-06-11"]="Mürzsteger Alpen"

    # Tyrol (AT-07)
    ["AT-07-04-01"]="Karwendel West"
    ["AT-07-10"]="Verwallgruppe Mitte"
    ["AT-07-12"]="Silvretta Ost"
    ["AT-07-14-01"]="Kaunergrat"
    ["AT-07-14-02"]="Kühtai - Geigenkamm"
    ["AT-07-14-03"]="Sellrain - Alpeiner Berge"
    ["AT-07-14-04"]="Kalkkögel"
    ["AT-07-14-05"]="Serleskamm"
    ["AT-07-15"]="Tuxer Alpen West"
    ["AT-07-17-01"]="Kitzbüheler Alpen Brixental"
    ["AT-07-20"]="Weißkugelgruppe"
    ["AT-07-21"]="Gurgler Gruppe"
    ["AT-07-22"]="Stubaier Alpen Mitte"
    ["AT-07-23-01"]="Zillertaler Alpen Nordwest"

    # Carinthia (AT-02)
    ["AT-02-01-01"]="Glocknergruppe Pasterze"
    ["AT-02-01-02-01"]="Goldberggruppe Süd"
    ["AT-02-01-02-02"]="Sadniggruppe"
    ["AT-02-02"]="Schobergruppe Ost"
    ["AT-02-03-01-01"]="Ankogel- Hochalmgruppe"
    ["AT-02-03-01-02"]="Reisseckgruppe"
    ["AT-02-03-02"]="Hafnergruppe"
    ["AT-02-04-01"]="Nockberge Mitte"
    ["AT-02-04-02"]="Nockberge Süd"

    # Vorarlberg (AT-08)
    ["AT-08-03-01"]="Allgäuer Alpen"
    ["AT-08-04"]="Silvretta - Samnaun"
    ["AT-08-05-01"]="Verwall"
    ["AT-08-06"]="Rätikon"
)

# === Helper Functions ===

# Display locations grouped by region
show_locations_by_region() {
    local -A by_region
    local loc region
    for loc in "${!LOCATIONS[@]}"; do
        IFS=',' read -r _ _ region _ <<< "${LOCATIONS[$loc]}"
        by_region[$region]+="$loc "
    done

    echo "Available locations:"
    # Display in consistent order (Tyrol first as most popular)
    for region in AT-07 AT-02 AT-08 AT-03 AT-06; do
        case "$region" in
            AT-07) echo -n "  Tyrol:          " ;;
            AT-02) echo -n "  Carinthia:      " ;;
            AT-08) echo -n "  Vorarlberg:     " ;;
            AT-03) echo -n "  Lower Austria:  " ;;
            AT-06) echo -n "  Styria:         " ;;
        esac
        echo "${by_region[$region]}"
    done
}

show_usage() {
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

EOF
    show_locations_by_region
}

usage() {
    show_usage
    exit 0
}

usage_error() {
    show_usage >&2
    exit 1
}

# Get avalanche bulletin from appropriate API
# AT-02 (Carinthia) and AT-07 (Tyrol) use static.avalanche.report
# AT-03, AT-06, AT-08 use static.lawinen-warnung.eu
get_avalanche_data() {
    local region_code="$1"  # e.g., AT-03
    local micro_region="$2"  # e.g., AT-03-04

    local url response
    local today
    today=$(date +%Y-%m-%d)

    # Select API based on region
    case "$region_code" in
        AT-02|AT-07)
            url="https://static.avalanche.report/bulletins/${today}/${region_code}.json"
            ;;
        *)
            url="https://static.lawinen-warnung.eu/bulletins/latest/${region_code}.json"
            ;;
    esac

    # 10s timeout balances responsiveness with reliability for API calls
    if ! response=$(curl -sf --max-time 10 "$url" 2>/dev/null); then
        echo "Error: Failed to fetch avalanche data for $region_code" >&2
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
# Returns: snow depth in cm, or "N/A" if unavailable
# Exit code: 0 on success, 1 on failure
get_snow_depth() {
    local lat="$1"
    local lon="$2"

    # SNOWGRID data is 1 day behind, so query yesterday
    local yesterday
    yesterday=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)

    local url="https://dataset.api.hub.geosphere.at/v1/timeseries/historical/snowgrid_cl-v2-1d-1km"
    url+="?parameters=snow_depth&lat_lon=${lat},${lon}&start=${yesterday}&end=${yesterday}&output_format=csv"

    local response
    if ! response=$(curl -sf --max-time 10 "$url" 2>/dev/null); then
        echo "N/A"
        return 1
    fi

    # Parse CSV - get the last snow_depth value
    local depth
    depth=$(echo "$response" | tail -1 | cut -d',' -f2 | tr -d ' ')

    if [[ -z "$depth" || "$depth" == "snow_depth" ]]; then
        # No data available (header only or empty)
        echo "N/A"
        return 1
    else
        # Convert from meters to cm
        printf "%.0f" "$(echo "$depth * 100" | bc -l 2>/dev/null || echo "0")"
    fi
}

# Get weather forecast from Open-Meteo ICON-D2
# Exit code: 0 on success, 1 on failure
get_weather() {
    local lat="$1"
    local lon="$2"

    local url="https://api.open-meteo.com/v1/dwd-icon"
    url+="?latitude=${lat}&longitude=${lon}"
    url+="&hourly=temperature_2m,windspeed_10m,winddirection_10m,precipitation_probability,cloudcover"
    url+="&models=icon_d2"
    url+="&forecast_days=2"  # ICON-D2 model provides 48h forecasts
    url+="&timezone=Europe/Vienna"

    local response
    if ! response=$(curl -sf --max-time 10 "$url" 2>/dev/null); then
        return 1
    fi
    echo "$response"
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
    if avy_data=$(get_avalanche_data "$region_code" "$micro_region") && \
       [[ "$avy_data" != *"unavailable"* ]]; then
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
        # Show validity with staleness warning if bulletin is outdated
        if [[ -n "$valid" ]]; then
            local today
            today=$(date +%Y-%m-%d)
            if [[ "$valid" < "$today" ]]; then
                echo "   Valid until: $valid  ⚠️ (bulletin may be outdated)"
            else
                echo "   Valid until: $valid"
            fi
        fi
    else
        echo "   ❌ Avalanche data unavailable"
    fi
    echo

    # Snow depth
    echo "❄️  SNOW DEPTH"
    echo "─────────────────────────────────────────────────────────────────"
    local snow_cm
    if snow_cm=$(get_snow_depth "$lat" "$lon") && [[ "$snow_cm" != "N/A" ]]; then
        echo "   Current: ${snow_cm} cm (SNOWGRID, 1 day behind)"
    else
        echo "   ❌ Snow depth data unavailable"
    fi
    echo

    # Weather
    echo "🌤️  WEATHER FORECAST"
    echo "─────────────────────────────────────────────────────────────────"
    local weather_json
    if weather_json=$(get_weather "$lat" "$lon"); then
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
        echo "   ❌ Weather data unavailable"
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
            *)
                echo "Error: Unknown option: $1" >&2
                echo "Use --help for usage information" >&2
                exit 1
                ;;
        esac
    done

    # === Argument Validation ===

    # Check for partial coordinates
    if [[ -n "$lat" && -z "$lon" ]] || [[ -z "$lat" && -n "$lon" ]]; then
        echo "Error: Both --lat and --lon are required for coordinate lookup" >&2
        exit 1
    fi

    # Validate lat/lon format and range
    if [[ -n "$lat" ]]; then
        # Stricter regex: requires digits before decimal, optional decimal with digits after
        if ! [[ "$lat" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
            echo "Error: Invalid latitude format: $lat (expected decimal degrees)" >&2
            exit 1
        fi
        if ! [[ "$lon" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
            echo "Error: Invalid longitude format: $lon (expected decimal degrees)" >&2
            exit 1
        fi
    fi

    # Handle compare mode
    if [[ -n "$compare" ]]; then
        IFS=',' read -ra locs <<< "$compare"
        for loc in "${locs[@]}"; do
            loc="${loc,,}"  # lowercase
            loc="${loc// /}"  # remove spaces
            if [[ -v "LOCATIONS[$loc]" ]]; then
                IFS=',' read -r lat lon region micro_region <<< "${LOCATIONS[$loc]}"
                show_location "$loc" "$lat" "$lon" "$region" "$micro_region"
            else
                echo "Error: Unknown location: $loc" >&2
                echo "Available: ${!LOCATIONS[*]}" >&2
            fi
        done
        exit 0
    fi

    # Single location mode
    if [[ -n "$location" ]]; then
        if [[ -v "LOCATIONS[$location]" ]]; then
            IFS=',' read -r lat lon region micro_region <<< "${LOCATIONS[$location]}"
            show_location "$location" "$lat" "$lon" "$region" "$micro_region"
        else
            echo "Error: Unknown location: $location" >&2
            echo "Available: ${!LOCATIONS[*]}" >&2
            exit 1
        fi
    elif [[ -n "$lat" && -n "$lon" ]]; then
        # Coordinate lookup using EAWS polygon data
        local script_dir
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        local lookup_script="${script_dir}/region_lookup.py"

        if [[ ! -f "$lookup_script" ]]; then
            echo "Error: region_lookup.py not found at $lookup_script" >&2
            echo "Use --location with a known location: ${!LOCATIONS[*]}" >&2
            exit 1
        fi

        # Check for uv (only needed for coordinate lookup)
        if ! command -v uv &>/dev/null; then
            echo "Error: uv is required for coordinate lookup" >&2
            echo "Install: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
            exit 1
        fi

        local result
        if ! result=$(uv run --script "$lookup_script" "$lat" "$lon"); then
            echo "Error: Could not determine avalanche region for coordinates ($lat, $lon)" >&2
            echo "The location may be outside covered Austrian alpine regions." >&2
            echo "Use --location with a known location: ${!LOCATIONS[*]}" >&2
            exit 1
        fi

        local region micro_region
        region=$(echo "$result" | jq -r '.region_code')
        micro_region=$(echo "$result" | jq -r '.micro_region')

        show_location "custom ($lat,$lon)" "$lat" "$lon" "$region" "$micro_region"
    else
        usage_error
    fi
}

main "$@"
