# SPDX-FileCopyrightText: 2026 Weather Clock for Matrix Portal
# SPDX-License-Identifier: MIT
# JJV

"""
Digital Clock with Weather Display
- Syncs time with Adafruit IO periodically
- Displays current weather from Open-Meteo
- Shows temperature and conditions
- Scrolling text for weather info
"""

# -- FEATURE FLAGS -----------------------------------------------------------
# Toggle True/False to enable or disable individual subsystems.
# Disabling a feature also skips its imports, saving memory on the M4.
# Stable baseline for Matrix Portal + HUB75:
# - Keep the DHT11 disabled by default. Its pulse timing can visibly disturb
#   panel refresh on this hardware even if the rest of the clock is static.
DEBUG_MODE             = False   # Bypass WiFi and use dummy data for layout testing
ENABLE_OUTDOOR_WEATHER = True   # Fetch outdoor temp/conditions from Open-Meteo
ENABLE_TIME_SYNC       = True   # Sync RTC from HTTP Date header (requires WiFi)
ENABLE_INDOOR_SENSOR   = False  # Read indoor temp/humidity from DHT11 on A1
ENABLE_WEATHER_OVERLAY = False   # Show periodic weather detail overlay screen
ENABLE_AUTO_BRIGHTNESS = False   # Dim display automatically at night
ENABLE_STARTUP_SCREEN  = False   # Show boot status screen before handing off to the clock
DHT_INIT_PER_READ      = True   # Create/release DHT object per read to reduce panel timing conflicts
FAST_POLLING_MODE      = False  # Use short test intervals instead of production-safe polling
INDOOR_SENSOR_MODE     = "off"  # "off", "boot_only", or "periodic"
FIXED_BRIGHTNESS       = 0.05   # Used when auto-brightness is disabled (0.0 to 1.0)
COLOR_SCALE            = 0.10   # Multiply all UI RGB colors by this factor

# Render strategy flags: keep these lightweight by default on HUB75 panels.
USE_SINGLE_WEATHER_STATUS_ICON = True   # Keep only one top-right weather icon mounted
USE_SINGLE_OUTDOOR_ICON        = True   # Keep only one sun/snow icon mounted

# -- TIMING ------------------------------------------------------------------
TIME_DISPLAY_DURATION         = 30    # seconds on main screen before weather overlay
TIME_SYNC_INTERVAL            = 3600  # seconds between RTC syncs (1 hour)
WEATHER_DISPLAY_DURATION      = 8     # seconds to show weather overlay
SCROLL_SPEED                  = 0.15  # seconds per pixel for scrolling text
WIFI_INITIAL_SETTLE_DELAY     = 2.5   # seconds for ESP32 radio to finish boot-time scan
WIFI_RETRY_DELAY              = 2.0   # base delay between WiFi retries
WIFI_RESET_AFTER_FAILURES     = 3     # reset ESP32 radio after this many failed attempts

if FAST_POLLING_MODE:
    WEATHER_UPDATE_INTERVAL       = 15   # seconds between outdoor weather fetches
    TEMP_HUMIDITY_UPDATE_INTERVAL = 5    # seconds between DHT11 sensor reads
else:
    WEATHER_UPDATE_INTERVAL       = 600  # production-safe: refresh outdoor weather every 10 minutes
    TEMP_HUMIDITY_UPDATE_INTERVAL = 30   # indoor readings do not need to run every few seconds

if INDOOR_SENSOR_MODE not in ("off", "boot_only", "periodic"):
    INDOOR_SENSOR_MODE = "off"

if not ENABLE_INDOOR_SENSOR:
    INDOOR_SENSOR_MODE = "off"

ENABLE_INDOOR_SENSOR = ENABLE_INDOOR_SENSOR and INDOOR_SENSOR_MODE != "off"

# -- IMPORTS -----------------------------------------------------------------
from os import getenv
import time
import board
import displayio
import terminalio
from adafruit_matrixportal.matrix import Matrix
from adafruit_bitmap_font import bitmap_font
import adafruit_display_text.label
from rtc import RTC

_needs_wifi = (ENABLE_OUTDOOR_WEATHER or ENABLE_TIME_SYNC) and not DEBUG_MODE
if _needs_wifi:
    import busio
    from digitalio import DigitalInOut
    import adafruit_connection_manager
    import adafruit_requests
    from adafruit_esp32spi import adafruit_esp32spi

if ENABLE_INDOOR_SENSOR:
    import adafruit_dht

# -- LOCATION / CREDENTIALS --------------------------------------------------
ssid          = getenv("CIRCUITPY_WIFI_SSID")
password      = getenv("CIRCUITPY_WIFI_PASSWORD")
latitude      = getenv("latitude", "42.9978")
longitude     = getenv("longitude", "-77.5194")
timezone_name = getenv("timezone", "America/New_York")
aio_username  = getenv("ADAFRUIT_AIO_USERNAME")
aio_key       = getenv("ADAFRUIT_AIO_KEY")

print("Weather Clock Starting...")
print(f"Location: {latitude}, {longitude}")
print(f"Timezone: {timezone_name}")

# -- DISPLAY INIT ------------------------------------------------------------
MATRIX  = Matrix(bit_depth=6)
DISPLAY = MATRIX.display

def scale_color(color, factor=COLOR_SCALE):
    """Scale a 24-bit RGB color without changing the overall palette choices."""
    red = int(((color >> 16) & 0xFF) * factor)
    green = int(((color >> 8) & 0xFF) * factor)
    blue = int((color & 0xFF) * factor)
    return (red << 16) | (green << 8) | blue

# Startup screen shown during boot so the matrix can be used for troubleshooting
# without a serial connection. Uses terminalio.FONT (always available).
_startup_group = displayio.Group()
_s_title  = adafruit_display_text.label.Label(
    terminalio.FONT, color=scale_color(0x005555), text="Wx Clock", x=10, y=6)
_s_status = adafruit_display_text.label.Label(
    terminalio.FONT, color=scale_color(0x009999), text="Starting...", x=2, y=17)
_s_detail = adafruit_display_text.label.Label(
    terminalio.FONT, color=scale_color(0x005555), text="          ", x=2, y=27)
_startup_group.append(_s_title)
_startup_group.append(_s_status)
_startup_group.append(_s_detail)
if ENABLE_STARTUP_SCREEN:
    DISPLAY.root_group = _startup_group
    DISPLAY.brightness = 0.05 #OLd 0.4
else:
    DISPLAY.brightness = FIXED_BRIGHTNESS

_STARTUP_W = 10

def set_startup_status(status, detail=""):
    """Pad/truncate to fixed width so the bitmap never resizes, avoiding flicker."""
    s = status[:_STARTUP_W]
    d = detail[:_STARTUP_W]
    _s_status.text = s + " " * (_STARTUP_W - len(s))
    _s_detail.text = d + " " * (_STARTUP_W - len(d))

# -- STATE VARIABLES ---------------------------------------------------------
ok = 0
err = 0
bad = 0
indoor_temp          = 100 if DEBUG_MODE else None
indoor_humidity      = 100 if DEBUG_MODE else None
active_brightness    = None
sensor_read_interval = TEMP_HUMIDITY_UPDATE_INTERVAL
last_main_display_state = None

if ENABLE_INDOOR_SENSOR:
    dht = None

def init_dht_sensor():
    """Create the DHT object only when needed.

    Keeping the DHT driver alive all the time can interfere with HUB75 refresh
    timing on Matrix Portal, so we support a per-read lifecycle by default.
    """
    global dht
    if not ENABLE_INDOOR_SENSOR or DEBUG_MODE:
        return None
    if dht is None:
        dht = adafruit_dht.DHT11(board.A1)
    return dht

def release_dht_sensor():
    """Release DHT timing resources so the matrix can refresh normally."""
    global dht
    if dht is not None:
        try:
            dht.exit()
        except Exception:
            pass
        dht = None

# -- WIFI INIT ---------------------------------------------------------------
esp      = None
requests = None
pool     = None
ssl_context = None
if _needs_wifi:
    esp32_cs    = DigitalInOut(board.ESP_CS)
    esp32_ready = DigitalInOut(board.ESP_BUSY)
    esp32_reset = DigitalInOut(board.ESP_RESET)

    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
    esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

    def rebuild_requests_session():
        global pool, ssl_context, requests
        pool        = adafruit_connection_manager.get_radio_socketpool(esp)
        ssl_context = adafruit_connection_manager.get_radio_ssl_context(esp)
        requests    = adafruit_requests.Session(pool, ssl_context)

    def reset_wifi_radio():
        global esp
        print("Resetting ESP32 WiFi radio...")
        set_startup_status("WiFi reset")
        try:
            esp32_reset.value = False
            time.sleep(0.15)
            esp32_reset.value = True
            time.sleep(0.75)
        except Exception as e:
            print(f"ESP32 reset pulse failed: {e}")
        esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
        rebuild_requests_session()

    def wifi_error_summary(error):
        text = str(error)
        if "No such ssid" in text:
            return "No SSID"
        if "ETIMEDOUT" in text or "timed out" in text.lower():
            return "Timeout"
        return text[:10]

    def connect_wifi(max_attempts=10, startup=False):
        if esp and esp.is_connected:
            return True

        phase_label = "WiFi..." if startup else "WiFi reconn"
        print("Connecting to WiFi..." if startup else "Reconnecting WiFi...")
        set_startup_status(phase_label, (ssid or "")[:10])
        time.sleep(WIFI_INITIAL_SETTLE_DELAY if startup else 1.0)

        consecutive_failures = 0
        for attempt in range(max_attempts):
            try:
                esp.connect_AP(ssid, password)
                print(f"Connected to {esp.ap_info.ssid}")
                print(f"IP address: {esp.ipv4_address}")
                set_startup_status("WiFi OK", str(esp.ipv4_address))
                return True
            except OSError as e:
                consecutive_failures += 1
                summary = wifi_error_summary(e)
                print(f"WiFi attempt {attempt + 1} failed: {e}")
                set_startup_status("WiFi retry", summary[:10])

                if consecutive_failures >= WIFI_RESET_AFTER_FAILURES:
                    reset_wifi_radio()
                    consecutive_failures = 0

                delay = WIFI_RETRY_DELAY
                if "No such ssid" in str(e):
                    delay += min(attempt, 4)
                time.sleep(delay)

        return False

    rebuild_requests_session()
    if not connect_wifi(startup=True):
        raise RuntimeError("Unable to connect to WiFi after multiple attempts")
elif DEBUG_MODE:
    print("DEBUG MODE: Skipping WiFi initialization")
    set_startup_status("Debug mode", "no WiFi")

def ensure_wifi_connected():
    if not _needs_wifi:
        return True
    if esp and esp.is_connected:
        return True
    return connect_wifi(max_attempts=6, startup=False)

# -- TIME SYNC ---------------------------------------------------------------
_MONTHS = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,
           'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}

def _set_rtc_from_http_date(date_str, utc_offset_seconds):
    """Parse RFC 7231 Date header (UTC) + apply offset, then set RTC.
    date_str format: 'Sun, 22 Feb 2026 15:30:00 GMT'
    Python's // and % handle negative offsets (e.g. UTC-5) correctly.
    Note: day rollover across a month boundary is not handled (rare, non-critical)."""
    parts = date_str.strip().split()
    day   = int(parts[1])
    month = _MONTHS[parts[2]]
    year  = int(parts[3])
    h, m, s = [int(x) for x in parts[4].split(':')]
    total    = h * 3600 + m * 60 + s + utc_offset_seconds
    day     += total // 86400
    total    = total % 86400
    hour     = total // 3600
    minute   = (total % 3600) // 60
    second   = total % 60
    rtc.datetime = time.struct_time((year, month, day, hour, minute, second, 0, -1, -1))
    print(f"RTC set: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d} local")

def sync_time():
    """Sync RTC from the HTTP Date header returned by Open-Meteo."""
    if not ensure_wifi_connected():
        return False
    for attempt in range(3):
        response = None
        try:
            print("Syncing time from Open-Meteo response header...")
            url = (f"http://api.open-meteo.com/v1/forecast"
                   f"?latitude={latitude}&longitude={longitude}"
                   f"&current=temperature_2m&timezone=auto&forecast_days=1")
            response = requests.get(url)
            date_str   = response.headers.get('Date') or response.headers.get('date', '')
            data       = response.json()
            utc_offset = data.get('utc_offset_seconds', 0)
            if not date_str:
                raise ValueError("No Date header in Open-Meteo response")
            _set_rtc_from_http_date(date_str, utc_offset)
            return True
        except Exception as e:
            print(f"Time sync attempt {attempt + 1} failed: {e}")
            time.sleep(2)
        finally:
            if response:
                response.close()
    return False

# -- FONTS -------------------------------------------------------------------
try:
    LARGE_FONT = bitmap_font.load_font('/fonts/Eight-Bit-Dragon-9-10.bdf')
    SMALL_FONT = bitmap_font.load_font('/fonts/6x10.bdf')
    print("Fonts loaded")
except Exception as e:
    print(f"Could not load custom fonts, using default: {e}")
    LARGE_FONT = terminalio.FONT
    SMALL_FONT = terminalio.FONT

def preload_font_glyphs(font, glyphs):
    """Preload glyphs once so first-use rendering doesn't stutter on the matrix."""
    if hasattr(font, "load_glyphs"):
        try:
            font.load_glyphs(glyphs)
        except Exception as e:
            print(f"Glyph preload skipped: {e}")

# -- ICONS -------------------------------------------------------------------
def create_icon_bitmaps():
    """Create small icons for outdoor, indoor, humidity, and weather status."""

    sun_bitmap = displayio.Bitmap(6, 8, 2)
    sun_palette = displayio.Palette(2)
    sun_palette[0] = 0x000000
    sun_palette[1] = scale_color(0xBB8800)
    sun_pattern = [
        0b001000,
        0b101010,
        0b011100,
        0b111110,
        0b111110,
        0b011100,
        0b101010,
        0b001000,
    ]
    for y, row in enumerate(sun_pattern):
        for x in range(6):
            if row & (1 << (5 - x)):
                sun_bitmap[x, y] = 1

    snow_bitmap = displayio.Bitmap(6, 8, 2)
    snow_palette = displayio.Palette(2)
    snow_palette[0] = 0x000000
    snow_palette[1] = scale_color(0x4466AA)
    snow_pattern = [
        0b001000,
        0b111110,
        0b011100,
        0b101010,
        0b011100,
        0b111110,
        0b001000,
        0b000000,
    ]
    for y, row in enumerate(snow_pattern):
        for x in range(6):
            if row & (1 << (5 - x)):
                snow_bitmap[x, y] = 1

    house_bitmap = displayio.Bitmap(6, 8, 2)
    house_palette = displayio.Palette(2)
    house_palette[0] = 0x000000
    house_palette[1] = scale_color(0x884433)
    house_pattern = [
        0b001000,
        0b011100,
        0b111110,
        0b111110,
        0b110110,
        0b110110,
        0b110110,
        0b111110,
    ]
    for y, row in enumerate(house_pattern):
        for x in range(6):
            if row & (1 << (5 - x)):
                house_bitmap[x, y] = 1

    drop_bitmap = displayio.Bitmap(6, 8, 2)
    drop_palette = displayio.Palette(2)
    drop_palette[0] = 0x000000
    drop_palette[1] = scale_color(0x336688)
    drop_pattern = [
        0b001000,
        0b011100,
        0b011100,
        0b111110,
        0b111110,
        0b111110,
        0b011100,
        0b000000,
    ]
    for y, row in enumerate(drop_pattern):
        for x in range(6):
            if row & (1 << (5 - x)):
                drop_bitmap[x, y] = 1

    # === WEATHER STATUS ICONS (15x10 pixels for upper right) ===

    clear_bitmap = displayio.Bitmap(15, 10, 3)
    clear_palette = displayio.Palette(3)
    clear_palette[0] = 0x000000
    clear_palette[1] = scale_color(0xCC9900)
    clear_palette[2] = scale_color(0x996600)
    clear_pattern = [
        [0,0,0,0,1,0,0,0,1,0,0,0,0,0,0],
        [0,0,0,2,0,0,0,0,0,2,0,0,0,0,0],
        [0,0,1,1,1,1,1,1,1,1,1,0,0,0,0],
        [0,2,1,1,1,1,1,1,1,1,1,2,0,0,0],
        [0,0,1,1,1,1,1,1,1,1,1,0,0,0,0],
        [0,0,0,2,0,0,0,0,0,2,0,0,0,0,0],
        [0,0,0,0,1,0,0,0,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    ]
    for y, row in enumerate(clear_pattern):
        for x, val in enumerate(row):
            clear_bitmap[x, y] = val

    cloud_bitmap = displayio.Bitmap(15, 10, 3)
    cloud_palette = displayio.Palette(3)
    cloud_palette[0] = 0x000000
    cloud_palette[1] = scale_color(0x7799AA)
    cloud_palette[2] = scale_color(0x556677)
    cloud_pattern = [
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,0,0,1,1,1,0,0,0,0,0,0,0,0,0],
        [0,0,1,2,2,2,1,1,1,0,0,0,0,0,0],
        [0,1,2,2,2,2,2,2,2,1,0,0,0,0,0],
        [0,1,2,2,2,2,2,2,2,2,1,0,0,0,0],
        [1,2,2,2,2,2,2,2,2,2,1,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,1,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    ]
    for y, row in enumerate(cloud_pattern):
        for x, val in enumerate(row):
            cloud_bitmap[x, y] = val

    rain_bitmap = displayio.Bitmap(15, 10, 3)
    rain_palette = displayio.Palette(3)
    rain_palette[0] = 0x000000
    rain_palette[1] = scale_color(0x445566)
    rain_palette[2] = scale_color(0x335577)
    rain_pattern = [
        [0,0,0,1,1,1,0,0,0,0,0,0,0,0,0],
        [0,0,1,1,1,1,1,1,0,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,0,0,0,0,0,0],
        [0,0,1,1,1,1,1,1,0,0,0,0,0,0,0],
        [0,0,2,0,2,0,2,0,0,0,0,0,0,0,0],
        [0,0,0,2,0,2,0,2,0,0,0,0,0,0,0],
        [0,0,2,0,2,0,2,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    ]
    for y, row in enumerate(rain_pattern):
        for x, val in enumerate(row):
            rain_bitmap[x, y] = val

    snow_status_bitmap = displayio.Bitmap(15, 10, 3)
    snow_status_palette = displayio.Palette(3)
    snow_status_palette[0] = 0x000000
    snow_status_palette[1] = scale_color(0x667788)
    snow_status_palette[2] = scale_color(0xAABBCC)
    snow_status_pattern = [
        [0,0,0,1,1,1,0,0,0,0,0,0,0,0,0],
        [0,0,1,1,1,1,1,1,0,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,0,0,0,0,0,0],
        [0,0,1,1,1,1,1,1,0,0,0,0,0,0,0],
        [0,0,2,0,0,2,0,0,2,0,0,0,0,0,0],
        [0,0,0,2,0,0,2,0,0,0,0,0,0,0,0],
        [0,0,2,0,0,2,0,0,2,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    ]
    for y, row in enumerate(snow_status_pattern):
        for x, val in enumerate(row):
            snow_status_bitmap[x, y] = val

    thunder_bitmap = displayio.Bitmap(15, 10, 3)
    thunder_palette = displayio.Palette(3)
    thunder_palette[0] = 0x000000
    thunder_palette[1] = scale_color(0x404040)
    thunder_palette[2] = scale_color(0xBBBB00)
    thunder_pattern = [
        [0,0,0,1,1,1,0,0,0,0,0,0,0,0,0],
        [0,0,1,1,1,1,1,1,0,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,0,0,0,0,0,0],
        [0,0,1,1,2,1,1,1,0,0,0,0,0,0,0],
        [0,0,0,2,2,0,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,2,2,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,2,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    ]
    for y, row in enumerate(thunder_pattern):
        for x, val in enumerate(row):
            thunder_bitmap[x, y] = val

    fog_bitmap = displayio.Bitmap(15, 10, 3)
    fog_palette = displayio.Palette(3)
    fog_palette[0] = 0x000000
    fog_palette[1] = scale_color(0x666666)
    fog_palette[2] = scale_color(0x444444)
    fog_pattern = [
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [1,2,2,2,2,2,2,2,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,1,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [1,2,2,2,2,2,2,2,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    ]
    for y, row in enumerate(fog_pattern):
        for x, val in enumerate(row):
            fog_bitmap[x, y] = val

    return (sun_bitmap, sun_palette), (snow_bitmap, snow_palette), (house_bitmap, house_palette), (drop_bitmap, drop_palette), \
           (clear_bitmap, clear_palette), (cloud_bitmap, cloud_palette), (rain_bitmap, rain_palette), \
           (snow_status_bitmap, snow_status_palette), (thunder_bitmap, thunder_palette), (fog_bitmap, fog_palette)

# -- DISPLAY LAYOUT ----------------------------------------------------------
sun_icon, snow_icon, house_icon, drop_icon, clear_icon, cloud_icon, rain_icon, snow_status_icon, thunder_icon, fog_icon = create_icon_bitmaps()

main_group = displayio.Group()

# Time -- top left
time_label = adafruit_display_text.label.Label(
    LARGE_FONT, color=scale_color(0xCC8800), text='--:--', x=2, y=7)
main_group.append(time_label)

# AM/PM -- top middle
ampm_label = adafruit_display_text.label.Label(
    SMALL_FONT, color=scale_color(0x886633), text='--', x=34, y=7)
main_group.append(ampm_label)

# Weather status icons -- top right (15x10)
weather_status_clear   = displayio.TileGrid(clear_icon[0],       pixel_shader=clear_icon[1],       x=49, y=3)
weather_status_cloud   = displayio.TileGrid(cloud_icon[0],       pixel_shader=cloud_icon[1],       x=49, y=3)
weather_status_rain    = displayio.TileGrid(rain_icon[0],        pixel_shader=rain_icon[1],        x=49, y=3)
weather_status_snow    = displayio.TileGrid(snow_status_icon[0], pixel_shader=snow_status_icon[1], x=49, y=3)
weather_status_thunder = displayio.TileGrid(thunder_icon[0],     pixel_shader=thunder_icon[1],     x=49, y=3)
weather_status_fog     = displayio.TileGrid(fog_icon[0],         pixel_shader=fog_icon[1],         x=49, y=3)
if USE_SINGLE_WEATHER_STATUS_ICON:
    main_group.append(weather_status_clear)
    weather_status_icon_index = len(main_group) - 1
else:
    main_group.append(weather_status_clear);   weather_status_clear_index   = len(main_group) - 1
    main_group.append(weather_status_cloud);   weather_status_cloud_index   = len(main_group) - 1
    main_group.append(weather_status_rain);    weather_status_rain_index    = len(main_group) - 1
    main_group.append(weather_status_snow);    weather_status_snow_index    = len(main_group) - 1
    main_group.append(weather_status_thunder); weather_status_thunder_index = len(main_group) - 1
    main_group.append(weather_status_fog);     weather_status_fog_index     = len(main_group) - 1

    main_group[weather_status_clear_index].hidden   = False
    main_group[weather_status_cloud_index].hidden   = True
    main_group[weather_status_rain_index].hidden    = True
    main_group[weather_status_snow_index].hidden    = True
    main_group[weather_status_thunder_index].hidden = True
    main_group[weather_status_fog_index].hidden     = True

# Date -- middle left
date_label = adafruit_display_text.label.Label(
    SMALL_FONT, color=scale_color(0x887755), text='--/--', x=2, y=16)
main_group.append(date_label)

# Outdoor icon (sun/snow) + temperature -- middle right
sun_tilegrid  = displayio.TileGrid(sun_icon[0],  pixel_shader=sun_icon[1],  x=34, y=13)
snow_tilegrid = displayio.TileGrid(snow_icon[0], pixel_shader=snow_icon[1], x=34, y=13)
if USE_SINGLE_OUTDOOR_ICON:
    main_group.append(sun_tilegrid)
    outdoor_icon_index = len(main_group) - 1
else:
    main_group.append(sun_tilegrid);  outdoor_icon_sun_index  = len(main_group) - 1
    main_group.append(snow_tilegrid); outdoor_icon_snow_index = len(main_group) - 1
    main_group[outdoor_icon_sun_index].hidden  = False
    main_group[outdoor_icon_snow_index].hidden = True

outdoor_temp_label = adafruit_display_text.label.Label(
    SMALL_FONT, color=scale_color(0x997755), text=' --°', x=40, y=16)
main_group.append(outdoor_temp_label)

# Indoor temp + humidity -- bottom row
house_tilegrid = displayio.TileGrid(house_icon[0], pixel_shader=house_icon[1], x=2,  y=22)
main_group.append(house_tilegrid)

indoor_temp_label = adafruit_display_text.label.Label(
    SMALL_FONT, color=scale_color(0x996644), text=' --°', x=9, y=26)
main_group.append(indoor_temp_label)

drop_tilegrid = displayio.TileGrid(drop_icon[0], pixel_shader=drop_icon[1], x=34, y=23)
main_group.append(drop_tilegrid)

indoor_humid_label = adafruit_display_text.label.Label(
    SMALL_FONT, color=scale_color(0x337788), text=' --%', x=40, y=26)
main_group.append(indoor_humid_label)

# Weather overlay group -- switching DISPLAY.root_group atomically eliminates
# the per-element hide/show loops that caused flicker on HUB75 panels.
weather_overlay_group = displayio.Group()
weather_condition_label = adafruit_display_text.label.Label(
    SMALL_FONT, color=scale_color(0x998866), text='', x=2, y=5)
weather_current_label = adafruit_display_text.label.Label(
    SMALL_FONT, color=scale_color(0x997755), text='', x=2, y=16)
weather_tomorrow_label = adafruit_display_text.label.Label(
    SMALL_FONT, color=scale_color(0x557766), text='', x=2, y=26)
weather_overlay_group.append(weather_condition_label)
weather_overlay_group.append(weather_current_label)
weather_overlay_group.append(weather_tomorrow_label)

# -- RTC ---------------------------------------------------------------------
rtc = RTC()

# -- WEATHER CODES -----------------------------------------------------------
WEATHER_CODES = {
    0: "Clear",
    1: "Mostly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Foggy",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    56: "Frz Drizzle",
    57: "Frz Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    66: "Frz Rain",
    67: "Frz Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Light Showers",
    81: "Showers",
    82: "Heavy Showers",
    85: "Snow Showers",
    86: "Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm"
}

MAIN_FONT_GLYPHS  = " -:0123456789"
SMALL_FONT_GLYPHS = "".join(sorted(set(
    " %./:-0123456789AMPNowTom°" +
    "".join(WEATHER_CODES.values())
)))
preload_font_glyphs(LARGE_FONT, MAIN_FONT_GLYPHS)
preload_font_glyphs(SMALL_FONT, SMALL_FONT_GLYPHS)

# -- DISPLAY HELPERS ---------------------------------------------------------
def set_label_text(label, text):
    if label.text != text:
        label.text = text

def set_display_brightness(brightness):
    global active_brightness
    brightness = max(0.0, min(1.0, brightness))
    if active_brightness is None or abs(active_brightness - brightness) > 0.01:
        DISPLAY.brightness = brightness
        active_brightness  = brightness

def get_target_brightness(hour_24):
    if 7 <= hour_24 < 21:
        return 1.0
    if 21 <= hour_24 or hour_24 < 6:
        return 0.35
    return 0.65

def format_time_text(hour_24, minute):
    """Render a fixed-width 12-hour time string to avoid label reallocations."""
    am_pm = "AM"
    hour  = hour_24
    if hour >= 12:
        am_pm = "PM"
        if hour > 12:
            hour -= 12
    if hour == 0:
        hour = 12
    return "{:>2}:{:02d}".format(hour, minute), am_pm

def format_date_text(month, day):
    return "{:02d}/{:02d}".format(month, day)

def format_temp_text(temp):
    if temp is None:
        return " --°"
    return "{:>3.0f}°".format(temp)

def format_humidity_text(humidity):
    if humidity is None:
        return " --%"
    return "{:>3.0f}%".format(humidity)

def get_temp_color(temp):
    if temp is None:    return scale_color(0x555555)
    elif temp <= 20:    return scale_color(0x2244AA)
    elif temp <= 32:    return scale_color(0x3366CC)
    elif temp <= 40:    return scale_color(0x4488AA)
    elif temp <= 55:    return scale_color(0x448866)
    elif temp <= 70:    return scale_color(0x997722)
    elif temp <= 80:    return scale_color(0xAA6622)
    elif temp <= 90:    return scale_color(0xAA3322)
    return scale_color(0x881111)

def get_weather_status_tilegrid(condition):
    condition = condition.lower()
    if 'clear' in condition or 'sunny' in condition:
        return weather_status_clear
    if 'thunder' in condition or 'storm' in condition:
        return weather_status_thunder
    if 'rain' in condition or 'shower' in condition or 'drizzle' in condition:
        return weather_status_rain
    if 'snow' in condition:
        return weather_status_snow
    if 'fog' in condition or 'mist' in condition:
        return weather_status_fog
    if 'cloud' in condition or 'overcast' in condition:
        return weather_status_cloud
    return weather_status_clear

def set_weather_status_icon(icon_tilegrid):
    """Update the top-right weather icon using the configured render strategy."""
    if USE_SINGLE_WEATHER_STATUS_ICON:
        if main_group[weather_status_icon_index] is not icon_tilegrid:
            main_group[weather_status_icon_index] = icon_tilegrid
        return

    indices = [
        (weather_status_clear_index,   icon_tilegrid is weather_status_clear),
        (weather_status_cloud_index,   icon_tilegrid is weather_status_cloud),
        (weather_status_rain_index,    icon_tilegrid is weather_status_rain),
        (weather_status_snow_index,    icon_tilegrid is weather_status_snow),
        (weather_status_thunder_index, icon_tilegrid is weather_status_thunder),
        (weather_status_fog_index,     icon_tilegrid is weather_status_fog),
    ]
    for idx, should_show in indices:
        new_hidden = not should_show
        if main_group[idx].hidden != new_hidden:
            main_group[idx].hidden = new_hidden

def build_main_display_state(now):
    """Build the desired main-screen state without touching displayio."""
    time_text, am_pm = format_time_text(now.tm_hour, now.tm_min)
    date_text = format_date_text(now.tm_mon, now.tm_mday)

    if weather_data:
        temp = weather_data['temp']
        color = get_temp_color(temp)
        outdoor_text = format_temp_text(temp)
        outdoor_icon = snow_tilegrid if temp < 40 else sun_tilegrid
        status_icon = get_weather_status_tilegrid(weather_data['condition'])
    else:
        color = get_temp_color(None)
        outdoor_text = format_temp_text(None)
        outdoor_icon = sun_tilegrid
        status_icon = weather_status_clear

    return (
        time_text, am_pm, date_text, outdoor_text, color,
        outdoor_icon, status_icon,
        format_temp_text(indoor_temp), format_humidity_text(indoor_humidity),
    )

def apply_main_display_state(state):
    (time_text, am_pm, date_text, outdoor_text, outdoor_color,
     outdoor_icon, status_icon,
     indoor_temp_text, indoor_humid_text) = state

    set_label_text(time_label,         time_text)
    set_label_text(ampm_label,         am_pm)
    set_label_text(date_label,         date_text)
    set_label_text(outdoor_temp_label, outdoor_text)
    if outdoor_temp_label.color != outdoor_color:
        outdoor_temp_label.color = outdoor_color
    if USE_SINGLE_OUTDOOR_ICON:
        if main_group[outdoor_icon_index] is not outdoor_icon:
            main_group[outdoor_icon_index] = outdoor_icon
    else:
        show_sun = outdoor_icon is sun_tilegrid
        if main_group[outdoor_icon_sun_index].hidden == show_sun:
            main_group[outdoor_icon_sun_index].hidden = not show_sun
            main_group[outdoor_icon_snow_index].hidden = show_sun
    set_weather_status_icon(status_icon)
    set_label_text(indoor_temp_label,  indoor_temp_text)
    set_label_text(indoor_humid_label, indoor_humid_text)

def update_main_display(now):
    global last_main_display_state
    state = build_main_display_state(now)
    if state != last_main_display_state:
        apply_main_display_state(state)
        last_main_display_state = state

# -- WEATHER OVERLAY ---------------------------------------------------------
def show_weather_overlay_nonblocking():
    """State machine for weather overlay. Returns True while showing, False when done."""
    global weather_overlay_state, weather_overlay_start_time, weather_overlay_data

    if weather_overlay_state == "inactive":
        return False

    if weather_overlay_state == "start":
        if not weather_overlay_data:
            weather_overlay_state = "inactive"
            return False

        condition_text = weather_overlay_data['condition']
        current_text   = f"Now: {weather_overlay_data['temp']:.0f}°"
        tomorrow_text  = f"Tom: {weather_overlay_data['tomorrow_min']:.0f}-{weather_overlay_data['tomorrow_max']:.0f}°"

        set_label_text(weather_condition_label, condition_text)
        set_label_text(weather_current_label,   current_text)
        set_label_text(weather_tomorrow_label,  tomorrow_text)

        # Atomic switch to overlay -- no per-element show/hide needed
        DISPLAY.root_group         = weather_overlay_group
        weather_overlay_state      = "display"
        weather_overlay_start_time = time.monotonic()
        return True

    if weather_overlay_state == "display":
        elapsed = time.monotonic() - weather_overlay_start_time

        condition_text = weather_overlay_data['condition']
        current_text   = f"Now: {weather_overlay_data['temp']:.0f}°"
        tomorrow_text  = f"Tom: {weather_overlay_data['tomorrow_min']:.0f}-{weather_overlay_data['tomorrow_max']:.0f}°"

        def _scroll(label, text, phase):
            if len(text) > 10:
                max_scroll = max(0, len(text) * 6 - 60)
                sc  = ((elapsed + phase) * 0.5) % 4
                pos = 2 + int(-max_scroll * (sc / 2 if sc < 2 else (2 - sc / 2)))
                if label.x != pos:
                    label.x = pos

        _scroll(weather_condition_label, condition_text, 0)
        _scroll(weather_current_label,   current_text,   1)
        _scroll(weather_tomorrow_label,  tomorrow_text,  2)

        if elapsed >= WEATHER_DISPLAY_DURATION:
            weather_condition_label.x = 2
            weather_current_label.x   = 2
            weather_tomorrow_label.x  = 2
            update_main_display(time.localtime())
            DISPLAY.root_group    = main_group
            weather_overlay_state = "inactive"
            return False

        return True

# -- WEATHER FETCH -----------------------------------------------------------
def get_weather():
    if not ensure_wifi_connected():
        return None
    for attempt in range(3):
        response = None
        try:
            print("Fetching weather...")
            url = (f"http://api.open-meteo.com/v1/forecast"
                   f"?latitude={latitude}"
                   f"&longitude={longitude}"
                   f"&current=temperature_2m,weather_code"
                   f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
                   f"&temperature_unit=fahrenheit"
                   f"&timezone=auto"
                   f"&forecast_days=2")
            response = requests.get(url)
            data = response.json()

            current           = data['current']
            current_temp      = current['temperature_2m']
            current_code      = current['weather_code']
            current_condition = WEATHER_CODES.get(current_code, f"Code {current_code}")

            daily        = data['daily']
            tomorrow_max = daily['temperature_2m_max'][1]
            tomorrow_min = daily['temperature_2m_min'][1]

            print(f"Weather: {current_temp}°F, {current_condition} (wmo={current_code})")
            return {
                'temp':         current_temp,
                'condition':    current_condition,
                'tomorrow_max': tomorrow_max,
                'tomorrow_min': tomorrow_min
            }
        except Exception as e:
            print(f"Weather fetch attempt {attempt + 1} failed: {e}")
            time.sleep(2)
        finally:
            if response:
                response.close()
    return None

# -- INDOOR SENSOR -----------------------------------------------------------
def get_indoor_sensor_data():
    global ok, bad, indoor_temp, indoor_humidity, dht, sensor_read_interval
    try:
        sensor = init_dht_sensor()
        if sensor is None:
            return

        if sensor.temperature is None or sensor.humidity is None:
            print("DHT sensor read failed, attempting to reconnect...")
            release_dht_sensor()
            time.sleep(1)
            sensor = init_dht_sensor()
            if sensor is None:
                return

        t = sensor.temperature
        h = sensor.humidity

        if t is None or h is None:
            bad += 1
            print(f"BAD {bad}: got None (t={t}, h={h})")
        else:
            ok += 1
            indoor_temp          = t * 9 / 5 + 32
            indoor_humidity      = h
            sensor_read_interval = TEMP_HUMIDITY_UPDATE_INTERVAL
            print(f"OK {ok}: {t}C ({indoor_temp:.0f}F)  {h}%   (bad: {bad})")

    except RuntimeError as e:
        bad += 1
        sensor_read_interval = min(sensor_read_interval * 2, 60)
        print(f"ERR {bad}: {e}")
        release_dht_sensor()
        time.sleep(1)
    finally:
        if DHT_INIT_PER_READ:
            release_dht_sensor()

def maybe_read_indoor_sensor_once():
    """Read the indoor sensor only when the configured mode allows it."""
    if INDOOR_SENSOR_MODE == "off" or DEBUG_MODE:
        return
    get_indoor_sensor_data()

# -- TIMING VARIABLES --------------------------------------------------------
last_weather_update      = 0
last_time_sync           = 0
last_weather_display     = 0
last_time_display_start  = time.monotonic()
last_sensor_read         = 0
last_main_displayed_time = None
last_brightness          = None

weather_overlay_state      = "inactive"
weather_overlay_start_time = 0
weather_overlay_data       = None

# -- STARTUP INIT ------------------------------------------------------------
weather_data = None
if DEBUG_MODE:
    print("DEBUG MODE: Using dummy data for layout testing")
    set_startup_status("Debug", "dummy data")
    weather_data = {
        'temp': 100,
        'condition': 'Partly Cloudy with Showers',
        'tomorrow_max': 100,
        'tomorrow_min': 100
    }
    rtc.datetime = time.struct_time((2026, 12, 30, 10, 0, 0, 0, -1, -1))
else:
    if ENABLE_TIME_SYNC:
        set_startup_status("Time sync...")
        if sync_time():
            set_startup_status("Time OK")
        else:
            set_startup_status("Time failed", "no RTC sync")
        time.sleep(1)
    if ENABLE_OUTDOOR_WEATHER:
        set_startup_status("Weather...")
        weather_data = get_weather()
        if weather_data:
            set_startup_status("Weather OK", f"{weather_data['temp']:.0f}F")
        else:
            set_startup_status("Wx failed", "retrying...")
    if INDOOR_SENSOR_MODE == "boot_only":
        set_startup_status("Indoor...")
        maybe_read_indoor_sensor_once()

# Init complete -- hand off to main display
set_startup_status("Ready!")
time.sleep(0.3)
update_main_display(time.localtime())
initial_brightness = get_target_brightness(time.localtime().tm_hour) if ENABLE_AUTO_BRIGHTNESS else FIXED_BRIGHTNESS
DISPLAY.brightness = initial_brightness
active_brightness = initial_brightness
DISPLAY.root_group = main_group

# Reset timers AFTER init so the main loop doesn't immediately re-trigger
last_weather_update     = time.monotonic()
last_time_sync          = time.monotonic()
last_time_display_start = time.monotonic()

# -- MAIN LOOP ---------------------------------------------------------------
print("Starting main loop...")
while True:
    current_time = time.monotonic()

    if DEBUG_MODE:
        time.sleep(5)
        continue

    if ENABLE_TIME_SYNC and current_time - last_time_sync > TIME_SYNC_INTERVAL:
        sync_time()
        last_time_sync = current_time

    if ENABLE_OUTDOOR_WEATHER and current_time - last_weather_update > WEATHER_UPDATE_INTERVAL:
        new_weather = get_weather()
        if new_weather:
            weather_data = new_weather
        last_weather_update = current_time

    if INDOOR_SENSOR_MODE == "periodic" and current_time - last_sensor_read > sensor_read_interval:
        get_indoor_sensor_data()
        last_sensor_read = current_time

    if ENABLE_WEATHER_OVERLAY:
        if current_time - last_time_display_start > TIME_DISPLAY_DURATION:
            if weather_data and weather_overlay_state == "inactive":
                weather_overlay_data  = weather_data
                weather_overlay_state = "start"
            last_time_display_start = current_time
        if weather_overlay_state != "inactive":
            show_weather_overlay_nonblocking()

    now = time.localtime()
    if last_main_displayed_time is None or last_main_displayed_time.tm_min != now.tm_min:
        update_main_display(now)
        last_main_displayed_time = now

    if ENABLE_AUTO_BRIGHTNESS:
        target_brightness = get_target_brightness(now.tm_hour)
        if last_brightness != target_brightness:
            set_display_brightness(target_brightness)
            last_brightness = target_brightness
    else:
        if last_brightness != FIXED_BRIGHTNESS:
            set_display_brightness(FIXED_BRIGHTNESS)
            last_brightness = FIXED_BRIGHTNESS

    time.sleep(1)
