---
name: flights
description: Check real flight prices and schedules (Google Flights data via flight-goat CLI, plus Ryanair's exact APIs). Use for fare lookups, cheapest-date scans, and verifying route day-of-week patterns before booking.
allowed-tools: [Bash, Read]
user-invocable: true
---

# Flights — prices and schedules

Fare and schedule lookups without API keys. Two engines:

1. **`flight-goat-pp-cli`** — Google Flights data (all carriers), native Go, JSON output. The workhorse.
2. **Ryanair public API** — exact FR schedules and fares, authoritative for Ryanair-only questions.

## When to invoke

- "what do flights to X cost", "check flight prices", "cheapest day to fly"
- Verifying which weekdays a seasonal route operates before booking
- Comparing routings/dates for trip planning

## Prerequisite check

```bash
export PATH="$HOME/.local/bin:$PATH"
flight-goat-pp-cli --version || npx -y @mvanhorn/printing-press-library install flight-goat --cli-only
```

## Fare search (one-way; run twice for round trips)

```bash
flight-goat-pp-cli flights VIE EFL 2026-08-30 --currency EUR --stops non_stop
```

- Positional args: `<origin> <dest> <date>`. No `--adults` flag exists — prices are per person; multiply yourself.
- Useful flags: `--stops non_stop`, `--class business`, `--time 6-12` (departure window), `--airlines OS,FR`, `--sort cheapest`.
- Output is JSON: `.flights[] | {price, currency, stops, legs[].departure_time, legs[].arrival_time, legs[].airline}`. Parse with python3/jq; report price + times + carrier + stops.

## Cheapest-date scan

```bash
flight-goat-pp-cli dates VIE SMI --currency EUR
```

Scans a date range for the cheapest travel days — use when dates are flexible. See `dates --help` for range flags.

## Route discovery

```bash
flight-goat-pp-cli explore VIE   # nonstop destinations from an airport (Kayak data)
```

## Ryanair exact data (FR routes only)

Schedules (which weekdays a route flies, by month):

```bash
curl -s "https://www.ryanair.com/api/timtbl/3/schedules/VIE/CFU/years/2026/months/8"
```

Live one-way fares:

```bash
curl -s "https://www.ryanair.com/api/farfnd/v4/oneWayFares?departureAirportIataCode=VIE&arrivalAirportIataCode=CFU&outboundDepartureDateFrom=2026-08-28&outboundDepartureDateTo=2026-09-01&currency=EUR" | python3 -m json.tool
```

## Reporting conventions

- Default origin VIE, currency EUR, unless stated otherwise.
- Always name the carrier, exact times, and stops — not just the price.
- For thin seasonal routes (1–3×/week), say so explicitly: inventory risk beats price risk, and day-of-week patterns shift through the season — recommend verifying the exact dates in the carrier's booking engine before paying.
- Prices are the Google Flights search surface (or Ryanair's own): booking happens in the browser, not here.

## Known limitations

- `fast-flights` (Python) is broken from EU IPs (Google consent wall) — don't reach for it.
- Amadeus Self-Service API decommissioned 2026-07-17 — gone.
- Kayak/Skyscanner direct scraping is bot-walled — don't attempt.
- flight-goat occasionally returns localized airport names; that's cosmetic.
