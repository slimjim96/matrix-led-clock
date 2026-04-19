# SPDX-FileCopyrightText: 2026 Weather Clock for Matrix Portal
# SPDX-License-Identifier: MIT

"""
Digital Clock with Weather Display
- Syncs time with WorldTimeAPI periodically
- Displays current weather from Open-Meteo
- Shows temperature and conditions
- Scrolling text for weather info
"""
from os import getenv
import time
import board
import busio
import displayio
import terminalio
from digitalio import DigitalInOut
import adafruit_connection_manager
import adafruit_requests
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_matrixportal.matrix import Matrix
import adafruit_imageload
import adafruit_display_text.label
from rtc import RTC

# CONFIGURATION
WEATHER_UPDATE_INTERVAL = 5  # seconds (5 for testing, use 300+ for production)
TIME_SYNC_INTERVAL = 3600  # seconds (sync time every hour)
WEATHER_DISPLAY_DURATION = 3  # seconds to show detailed weather
FADE_STEPS = 10  # Number of steps in fade animation

# Get settings from settings.toml
ssid = getenv("CIRCUITPY_WIFI_SSID")
password = getenv("CIRCUITPY_WIFI_PASSWORD")
latitude = getenv("latitude", "42.9978")
longitude = getenv("longitude", "-77.5194")
timezone_name = getenv("timezone", "America/New_York")

print("Weather Clock Starting...")
print(f"Location: {latitude}, {longitude}")
print(f"Timezone: {timezone_name}")

# Initialize Matrix Display
MATRIX = Matrix(bit_depth=6)
DISPLAY = MATRIX.display

# Initialize ESP32 WiFi
esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)

spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

pool = adafruit_connection_manager.get_radio_socketpool(esp)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(esp)
requests = adafruit_requests.Session(pool, ssl_context)

# Connect to WiFi
print("Connecting to WiFi...")
while not esp.is_connected:
    try:
        esp.connect_AP(ssid, password)
    except OSError as e:
        print(f"Could not connect to AP, retrying: {e}")
        time.sleep(1)
        continue

print(f"Connected to {esp.ap_info.ssid}")
print(f"IP address: {esp.ipv4_address}")

# Load digit sprite sheet (using TileGrid approach for crisp display)
# Create a programmatic digit sprite sheet if no bitmap file exists
def create_digit_bitmap():
    """Create a simple digit sprite sheet in memory"""
    # Create a bitmap with 11 tiles: 0-9 and blank
    # Each digit is 8 pixels wide x 12 pixels tall
    palette = displayio.Palette(2)
    palette[0] = 0x000000  # Black/transparent
    palette[1] = 0x00FF00  # Green for digits
    
    # Create bitmap: 11 tiles x 8 pixels wide = 88 pixels wide, 12 pixels tall
    bitmap = displayio.Bitmap(88, 12, 2)
    
    # Define digits as simple patterns (8x12 each)
    # This is a simplified version - you can replace with actual digit bitmaps
    digits = [
        # 0
        [0b01111110, 0b11111111, 0b11000011, 0b11000011, 0b11000011, 
         0b11000011, 0b11000011, 0b11000011, 0b11000011, 0b11111111, 0b01111110, 0b00000000],
        # 1
        [0b00011000, 0b00111000, 0b01111000, 0b00011000, 0b00011000,
         0b00011000, 0b00011000, 0b00011000, 0b00011000, 0b11111111, 0b11111111, 0b00000000],
        # 2
        [0b01111110, 0b11111111, 0b11000011, 0b00000011, 0b00000110,
         0b00001100, 0b00011000, 0b00110000, 0b01100000, 0b11111111, 0b11111111, 0b00000000],
        # 3
        [0b01111110, 0b11111111, 0b11000011, 0b00000011, 0b00111110,
         0b00111110, 0b00000011, 0b00000011, 0b11000011, 0b11111111, 0b01111110, 0b00000000],
        # 4
        [0b00000110, 0b00001110, 0b00011110, 0b00110110, 0b01100110,
         0b11000110, 0b11111111, 0b11111111, 0b00000110, 0b00000110, 0b00000110, 0b00000000],
        # 5
        [0b11111111, 0b11111111, 0b11000000, 0b11000000, 0b11111110,
         0b11111111, 0b00000011, 0b00000011, 0b11000011, 0b11111111, 0b01111110, 0b00000000],
        # 6
        [0b01111110, 0b11111111, 0b11000000, 0b11000000, 0b11111110,
         0b11111111, 0b11000011, 0b11000011, 0b11000011, 0b11111111, 0b01111110, 0b00000000],
        # 7
        [0b11111111, 0b11111111, 0b00000011, 0b00000110, 0b00001100,
         0b00011000, 0b00110000, 0b00110000, 0b00110000, 0b00110000, 0b00110000, 0b00000000],
        # 8
        [0b01111110, 0b11111111, 0b11000011, 0b11000011, 0b01111110,
         0b01111110, 0b11000011, 0b11000011, 0b11000011, 0b11111111, 0b01111110, 0b00000000],
        # 9
        [0b01111110, 0b11111111, 0b11000011, 0b11000011, 0b11000011,
         0b11111111, 0b01111111, 0b00000011, 0b00000011, 0b11111111, 0b01111110, 0b00000000],
        # Blank (10)
        [0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000,
         0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000],
    ]
    
    # Draw each digit into the bitmap
    for digit_idx, digit_pattern in enumerate(digits):
        x_offset = digit_idx * 8
        for y, row in enumerate(digit_pattern):
            for x in range(8):
                if row & (1 << (7 - x)):
                    bitmap[x_offset + x, y] = 1
    
    return bitmap, palette

# Try to load digit bitmap from file, or create one
try:
    print("Loading digit sprite sheet...")
    digits_bmp, digits_pal = adafruit_imageload.load("/bmps/digits.bmp")
except Exception as e:
    print(f"Creating digit sprite sheet: {e}")
    digits_bmp, digits_pal = create_digit_bitmap()

# Use small font for labels
SMALL_FONT = terminalio.FONT

# Create display groups
# Main display group for time/date/temp
main_group = displayio.Group()

# Weather overlay group (for fade effect)
weather_group = displayio.Group()

# === MAIN DISPLAY LAYOUT (64x32) using TileGrids ===
# Top: Large time using TileGrid for crisp digits
# Time display: HH:MM (4 digits + colon)
# Create TileGrid for time - 5 positions (H H : M M)
time_digits = displayio.TileGrid(
    digits_bmp,
    pixel_shader=digits_pal,
    x=4,
    y=2,
    width=5,
    height=1,
    tile_width=8,
    tile_height=12
)
main_group.append(time_digits)

# Initialize time display to blanks
for i in range(5):
    time_digits[i] = 10  # Blank tile

# Add colon between hours and minutes
colon_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x00FF00,  # Green
    text=':',
    x=23,
    y=10
)
main_group.append(colon_label)

# Top right: AM/PM
ampm_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x00AA00,  # Dim green
    text='--',
    x=50,
    y=10
)
main_group.append(ampm_label)

# Middle: Date and outdoor temp using small TileGrid
date_temp_digits = displayio.TileGrid(
    digits_bmp,
    pixel_shader=digits_pal,
    x=2,
    y=16,
    width=8,
    height=1,
    tile_width=8,
    tile_height=12
)
main_group.append(date_temp_digits)

# Initialize date/temp display
for i in range(8):
    date_temp_digits[i] = 10  # Blank tile

# Bottom: Indoor sensors using TileGrid
indoor_digits = displayio.TileGrid(
    digits_bmp,
    pixel_shader=digits_pal,
    x=2,
    y=26,
    width=8,
    height=1,
    tile_width=8,
    tile_height=12
)
main_group.append(indoor_digits)

# Initialize indoor display
for i in range(8):
    indoor_digits[i] = 10  # Blank tile

# === WEATHER OVERLAY ===
# Weather overlay labels for text
weather_condition_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0xFFFFFF,  # White
    text='',
    x=2,
    y=8
)
weather_group.append(weather_condition_label)

weather_current_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0xFFAA00,  # Orange
    text='',
    x=2,
    y=17
)
weather_group.append(weather_current_label)

weather_tomorrow_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x40FF40,  # Light green
    text='',
    x=2,
    y=26
)
weather_group.append(weather_tomorrow_label)

# Start with main display
DISPLAY.root_group = main_group

# RTC for timekeeping
rtc = RTC()

# Timing variables
last_weather_update = 0
last_time_sync = 0
last_weather_display = 0
show_weather = False

# Indoor sensor placeholder values
indoor_temp = None  # Will be populated when sensor is connected
indoor_humidity = None  # Will be populated when sensor is connected

# Weather condition mapping
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
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Light Showers",
    81: "Showers",
    82: "Heavy Showers",
    85: "Light Snow",
    86: "Heavy Snow",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm"
}

def fade_brightness(group, start_brightness, end_brightness, steps=FADE_STEPS):
    """Fade display group brightness"""
    for i in range(steps + 1):
        brightness = start_brightness + (end_brightness - start_brightness) * i / steps
        DISPLAY.brightness = max(0.0, min(1.0, brightness))
        time.sleep(0.05)

def show_weather_overlay(weather_data):
    """Show detailed weather with fade animation"""
    if not weather_data:
        return
    
    # Update weather overlay text
    weather_condition_label.text = weather_data['condition']
    weather_current_label.text = f"Now: {weather_data['temp']:.0f}F"
    weather_tomorrow_label.text = f"Tom: {weather_data['tomorrow_min']:.0f}-{weather_data['tomorrow_max']:.0f}F"
    
    # Fade out main display
    fade_brightness(main_group, 1.0, 0.0)
    
    # Switch to weather overlay
    DISPLAY.root_group = weather_group
    
    # Fade in weather display
    fade_brightness(weather_group, 0.0, 1.0)
    
    # Hold weather display
    time.sleep(WEATHER_DISPLAY_DURATION)
    
    # Fade out weather display
    fade_brightness(weather_group, 1.0, 0.0)
    
    # Switch back to main display
    DISPLAY.root_group = main_group
    
    # Fade in main display
    fade_brightness(main_group, 0.0, 1.0)

def sync_time():
    """Sync time with WorldTimeAPI"""
    try:
        print("Syncing time...")
        url = f"http://worldtimeapi.org/api/timezone/{timezone_name}"
        response = requests.get(url)
        data = response.json()
        response.close()
        
        # Parse datetime string: 2026-01-18T15:30:45.123456-05:00
        datetime_str = data['datetime']
        date_part, time_part = datetime_str.split('T')
        year, month, day = date_part.split('-')
        time_only = time_part.split('.')[0]  # Remove microseconds
        time_only = time_only.split('-')[0].split('+')[0]  # Remove timezone
        hour, minute, second = time_only.split(':')
        
        # Get day of week (0=Monday, 6=Sunday in API)
        weekday = data['day_of_week']
        # Convert to struct_time format (0=Monday, 6=Sunday)
        
        current_time = time.struct_time((
            int(year), int(month), int(day),
            int(hour), int(minute), int(second),
            weekday, -1, -1
        ))
        
        rtc.datetime = current_time
        print(f"Time synced: {hour}:{minute}:{second}")
        return True
    except Exception as e:
        print(f"Error syncing time: {e}")
        return False

def get_weather():
    """Fetch weather from Open-Meteo API"""
    try:
        print("Fetching weather...")
        # Use HTTP instead of HTTPS to avoid SSL issues with ESP32
        url = (f"http://api.open-meteo.com/v1/forecast"
               f"?latitude={latitude}"
               f"&longitude={longitude}"
               f"&current=temperature_2m,weather_code"
               f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
               f"&temperature_unit=fahrenheit"
               f"&timezone=auto"
               f"&forecast_days=2")
        
        print(f"URL: {url}")
        response = requests.get(url)
        data = response.json()
        response.close()
        
        # Current weather
        current = data['current']
        current_temp = current['temperature_2m']
        current_code = current['weather_code']
        current_condition = WEATHER_CODES.get(current_code, "Unknown")
        
        # Tomorrow's forecast
        daily = data['daily']
        tomorrow_max = daily['temperature_2m_max'][1]
        tomorrow_min = daily['temperature_2m_min'][1]
        
        print(f"Current: {current_temp}°F, {current_condition}")
        print(f"Tomorrow: {tomorrow_min}°F - {tomorrow_max}°F")
        
        return {
            'temp': current_temp,
            'condition': current_condition,
            'tomorrow_max': tomorrow_max,
            'tomorrow_min': tomorrow_min
        }
    except Exception as e:
        print(f"Error fetching weather: {e}")
        return None

# Initial sync
sync_time()
time.sleep(1)
weather_data = get_weather()

# Main loop
print("Starting main loop...")
while True:
    current_time = time.monotonic()
    
    # Sync time periodically
    if current_time - last_time_sync > TIME_SYNC_INTERVAL:
        sync_time()
        last_time_sync = current_time
    
    # Update weather periodically
    if current_time - last_weather_update > WEATHER_UPDATE_INTERVAL:
        new_weather = get_weather()
        if new_weather:
            weather_data = new_weather
            # Show weather overlay with fade animation
            show_weather_overlay(weather_data)
        last_weather_update = current_time
    
    # Update time display using TileGrid
    now = time.localtime()
    hour = now.tm_hour
    minute = now.tm_min
    
    # Convert to 12-hour format
    am_pm = "AM"
    if hour >= 12:
        am_pm = "PM"
        if hour > 12:
            hour -= 12
    if hour == 0:
        hour = 12
    
    # Update time TileGrid: H H : M M
    # Position 0-1: Hour, Position 2: Colon (shown as 10/blank), Position 3-4: Minute
    hour_str = f"{hour:2d}"
    minute_str = f"{minute:02d}"
    
    # Update hour digits
    if hour < 10:
        time_digits[0] = 10  # Blank for single digit hour
        time_digits[1] = int(hour_str[1])
    else:
        time_digits[0] = int(hour_str[0])
        time_digits[1] = int(hour_str[1])
    
    # Colon position - use blank and add a label overlay for the colon
    time_digits[2] = 10  # Blank
    
    # Update minute digits
    time_digits[3] = int(minute_str[0])
    time_digits[4] = int(minute_str[1])
    
    # Update AM/PM
    ampm_label.text = am_pm
    
    # Update date/temp display - Format: M/DD TT (month/day temp)
    # This will display date and temp as digits
    month = now.tm_mon
    day = now.tm_mday
    
    # Clear the row first
    for i in range(8):
        date_temp_digits[i] = 10
    
    # Display month (1-2 digits)
    if month < 10:
        date_temp_digits[0] = month
        date_temp_digits[1] = 10  # Separator
    else:
        date_temp_digits[0] = month // 10
        date_temp_digits[1] = month % 10
    
    # Display day (always 2 digits)
    date_temp_digits[2] = day // 10
    date_temp_digits[3] = day % 10
    
    # Display outdoor temperature (2 digits)
    if weather_data:
        temp = int(weather_data['temp'])
        date_temp_digits[5] = temp // 10
        date_temp_digits[6] = temp % 10
        date_temp_digits[7] = 10  # F marker (blank for now)
    
    # Update indoor sensors display - Format: TT HH (temp humidity)
    # Clear the row
    for i in range(8):
        indoor_digits[i] = 10
    
    # Indoor temperature (2 digits)
    if indoor_temp is not None:
        temp = int(indoor_temp)
        indoor_digits[0] = temp // 10
        indoor_digits[1] = temp % 10
    else:
        indoor_digits[0] = 10  # Blank
        indoor_digits[1] = 10  # Blank
    
    # Indoor humidity (2 digits)
    if indoor_humidity is not None:
        humid = int(indoor_humidity)
        indoor_digits[4] = humid // 10
        indoor_digits[5] = humid % 10
    else:
        indoor_digits[4] = 10  # Blank
        indoor_digits[5] = 10  # Blank
    
    time.sleep(0.1)
