# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CircuitPython weather clock project running on an **Adafruit Matrix Portal M4** (SAMD51J19) driving a **64x32 P4 LED matrix** display. The D:\ drive is the CIRCUITPY USB mass storage volume — saving `code.py` causes the board to auto-reload and run it.

**Board**: Adafruit Matrix Portal M4 with ESP32 WiFi coprocessor
**Runtime**: CircuitPython 10.0.3

## Key Files

- `code.py` — **Active program** the board runs on boot. Currently: weather clock with outdoor weather (Open-Meteo API), indoor DHT11 sensor, time sync (Adafruit IO → WorldTimeAPI fallback), bitmap weather icons, and scrolling weather overlay with fade transitions.
- `code copy.py` / `code copy 2.py` / `code copy 3.py` — Earlier iterations of the weather clock (simpler layouts, TileGrid-based digits, no indoor sensor). Kept for reference/rollback.
- `clock_test.py` — Offline clock test with accelerometer auto-rotation and special effects (rainbow, blink, slide, zoom, matrix rain). No WiFi needed.
- `test_moon_api.py` — PC-side script (uses `requests`, not CircuitPython) to test MET Norway moon phase API connectivity.
- `settings.toml` — WiFi credentials, location (lat/lon), timezone, Adafruit IO credentials. **Contains secrets — never commit.**
- `lib/` — Pre-compiled `.mpy` Adafruit CircuitPython libraries (do not edit).
- `fonts/` — BDF bitmap fonts for the LED matrix display.

## Configuration

All configuration is in `settings.toml` (read via `os.getenv()` in CircuitPython):
- `CIRCUITPY_WIFI_SSID` / `CIRCUITPY_WIFI_PASSWORD` — 2.4GHz WPA2 only (no WPA3/6GHz)
- `latitude` / `longitude` — Location for weather data
- `timezone` — IANA timezone string for time sync
- `AIO_USERNAME` / `AIO_KEY` — Adafruit IO credentials for time sync

Tunable constants are at the top of `code.py`: `DEBUG_MODE`, `TIME_DISPLAY_DURATION`, `WEATHER_UPDATE_INTERVAL`, `TIME_SYNC_INTERVAL`, `WEATHER_DISPLAY_DURATION`, `TEMP_HUMIDITY_UPDATE_INTERVAL`, `FADE_STEPS`, `SCROLL_SPEED`.

## Architecture (code.py)

The main program follows a single-file, event-loop pattern typical of CircuitPython:

1. **Initialization**: Matrix display → WiFi (ESP32 SPI coprocessor) → fonts → bitmap icons → displayio groups
2. **Two display groups** swap via `DISPLAY.root_group`:
   - `main_group` — Clock face: time (large font), AM/PM, weather status icon (15x10 bitmap, upper-right), date, outdoor temp with sun/snowflake icon, indoor temp with house icon, indoor humidity with droplet icon
   - `weather_group` — Overlay: condition text, current temp, tomorrow forecast (with horizontal scroll for long text)
3. **Main loop** uses `time.monotonic()` timers for: time sync (hourly), weather API fetch, weather overlay display cycle, and DHT11 sensor reads
4. **Time sync** tries Adafruit IO first, falls back to WorldTimeAPI, sets the on-board RTC
5. **Weather** fetched from Open-Meteo via HTTP (not HTTPS — ESP32 SSL limitations)
6. **Indoor sensor**: DHT11 on pin A1, read every 5 seconds
7. **Icons**: Programmatically created as `displayio.Bitmap` pixel patterns (not loaded from files)
8. **DEBUG_MODE**: Skips WiFi, uses dummy data for layout testing on the physical display

## CircuitPython Constraints

- **No pip/packages**: Libraries go in `lib/` as pre-compiled `.mpy` files from the Adafruit bundle
- **Limited RAM**: ~192KB on SAMD51. Minimize object allocation in the main loop; reuse labels/bitmaps
- **No threading**: Single-threaded event loop with `time.sleep()` / `time.monotonic()` timing
- **No file write during execution**: The filesystem is read-only to the running code by default
- **HTTP responses must be `.close()`'d** to free sockets (ESP32 has limited socket pool)
- **`displayio` is the graphics framework**: Groups, TileGrids, Palettes, Bitmaps — not PIL/Pillow

## Display Layout (64x32 pixels)

```
+----------------------------------+---------------+
| HH:MM  AM/PM                    | Weather Icon  |
|                                  | (15x10)       |
+----------------------------------+---------------+
| MM/DD          [sun/snow] TTT°                   |
+--------------------------------------------------+
| [house] TT°        [drop] HH%                   |
+--------------------------------------------------+
```

## APIs Used

- **Open-Meteo** (`api.open-meteo.com/v1/forecast`) — Current weather + 2-day forecast, Fahrenheit, auto-timezone
- **Adafruit IO** (`io.adafruit.com/api/v2/.../integrations/time/iso`) — Primary time sync
- **WorldTimeAPI** (`worldtimeapi.org/api/timezone/...`) — Fallback time sync
- **MET Norway Sunrise API** (`api.met.no/weatherapi/sunrise/3.0/moon`) — Moon phase (used in test script only)
