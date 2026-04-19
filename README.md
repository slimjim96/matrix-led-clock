# CircuitPython Weather Clock

Weather clock for an Adafruit Matrix Portal M4 driving a 64x32 HUB75 LED matrix.

## Current Stable Profile

The current `code.py` defaults are intentionally conservative because this hardware
combination is sensitive to timing-heavy peripherals.

Recommended stable settings:

- `ENABLE_OUTDOOR_WEATHER = True`
- `ENABLE_TIME_SYNC = True`
- `ENABLE_INDOOR_SENSOR = False`
- `INDOOR_SENSOR_MODE = "off"`
- `ENABLE_WEATHER_OVERLAY = False`
- `ENABLE_AUTO_BRIGHTNESS = False`
- `ENABLE_STARTUP_SCREEN = False`
- `USE_SINGLE_WEATHER_STATUS_ICON = True`
- `USE_SINGLE_OUTDOOR_ICON = True`

These settings are the best-known non-flickery baseline for this Matrix Portal +
HUB75 display.

## Important Hardware Note

The DHT11 indoor sensor is the main known flicker source.

Why:

- DHT11 reads depend on very tight pulse timing.
- On the Matrix Portal, that timing can interfere with HUB75 refresh.
- When that happens, the matrix can look like it clears, flashes, or flickers.

Because of that, the indoor sensor is disabled by default.

## Indoor Sensor Modes

`code.py` supports three indoor sensor modes:

- `"off"`: no DHT reads, safest setting
- `"boot_only"`: take one read during startup only
- `"periodic"`: continue reading during normal operation

Recommended order for testing:

1. `ENABLE_INDOOR_SENSOR = True`
2. `INDOOR_SENSOR_MODE = "boot_only"`
3. Only try `"periodic"` if you are okay with possible flicker during reads

If you want reliable indoor readings without disturbing the display, an I2C sensor
such as `AHT20`, `SHT31-D`, or `BME280` is a better fit than `DHT11`.

## WiFi Notes

The ESP32 coprocessor sometimes reports:

- `('No such ssid', b'YOUR_SSID')`

even when the network exists.

The current code includes:

- a radio settle delay before the first connect
- retry backoff
- ESP32 radio reset after repeated failures

WiFi tuning lives near the top of `code.py`:

- `WIFI_INITIAL_SETTLE_DELAY`
- `WIFI_RETRY_DELAY`
- `WIFI_RESET_AFTER_FAILURES`

If startup still misses your network occasionally, try increasing
`WIFI_INITIAL_SETTLE_DELAY`.

## GitHub Push Script

The repo lives directly on the `CIRCUITPY` drive, so normal git use can be a bit
awkward. A helper script is included at:

- `push-to-github.ps1`

What it does:

- marks `D:/` as a git `safe.directory`
- stages all changes that are not ignored
- creates a commit
- pushes to the selected remote and branch

Example usage:

```powershell
powershell -ExecutionPolicy Bypass -File .\push-to-github.ps1 -Message "Update weather clock"
```

If the repo does not have a remote yet:

```powershell
powershell -ExecutionPolicy Bypass -File .\push-to-github.ps1 `
  -Message "Initial push" `
  -RemoteUrl "https://github.com/YOURNAME/YOURREPO.git"
```

Useful options:

- `-Message "..."`: commit message
- `-Branch main`: push a specific branch
- `-Remote origin`: choose a remote name
- `-RemoteUrl ...`: add or update the remote URL
- `-CommitOnly`: create the commit but do not push

The script is designed to run from the drive root and works around the Windows
ownership warning that can happen on removable/media-style filesystems.

## Feature Flags

The top of `code.py` is organized into:

- subsystem flags
- render strategy flags
- timing settings
- WiFi retry tuning

The most important flags are:

- `DEBUG_MODE`: bypass WiFi and use dummy weather/time data
- `ENABLE_OUTDOOR_WEATHER`: fetch current outdoor weather
- `ENABLE_TIME_SYNC`: sync RTC from Open-Meteo response time
- `ENABLE_INDOOR_SENSOR`: enable DHT-based indoor readings
- `ENABLE_WEATHER_OVERLAY`: show the full-screen weather detail overlay
- `ENABLE_AUTO_BRIGHTNESS`: adjust brightness by hour
- `ENABLE_STARTUP_SCREEN`: show boot status on the matrix before main UI
- `FAST_POLLING_MODE`: use short test intervals instead of production-safe ones

## Render Strategy

To reduce flicker, the clock now prefers lightweight display composition:

- one active top-right weather icon
- one active outdoor icon (sun or snow)
- a separate overlay group for the weather detail screen

Avoid switching back to a layout that keeps every alternate icon mounted and hidden
at the same time unless you specifically want to test that behavior.

## Files

- `code.py`: active program on the board
- `settings.toml`: credentials and location config
- `clock_test.py`: separate clock/effects test file
- `code copy.py`, `code copy 2.py`, `code copy 3.py`: earlier revisions kept for reference

## Safe Editing Workflow

Because this repo is the live `CIRCUITPY` drive:

- saving `code.py` reloads the board immediately
- small mistakes can reboot the device repeatedly
- changes to display structure should be tested one subsystem at a time

Suggested order when debugging future flicker:

1. Set `DEBUG_MODE = True`
2. Disable `ENABLE_INDOOR_SENSOR`
3. Disable `ENABLE_WEATHER_OVERLAY`
4. Keep `USE_SINGLE_WEATHER_STATUS_ICON = True`
5. Keep `USE_SINGLE_OUTDOOR_ICON = True`
6. Re-enable features one by one
