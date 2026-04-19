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
from adafruit_bitmap_font import bitmap_font
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

# Load fonts
try:
    LARGE_FONT = bitmap_font.load_font('/fonts/Eight-Bit-Dragon-11-15.bdf')
    SMALL_FONT = bitmap_font.load_font('/fonts/Eight-Bit-Dragon-9-10.bdf')
    print("Fonts loaded")
except Exception as e:
    print(f"Could not load custom fonts, using default: {e}")
    LARGE_FONT = terminalio.FONT
    SMALL_FONT = terminalio.FONT

# Create display groups
# Main display group for time/date/temp
main_group = displayio.Group()

# Weather overlay group (for fade effect)
weather_group = displayio.Group()

# === MAIN DISPLAY LAYOUT (64x32) ===
# Top: Large time (centered) - Line 1
time_label = adafruit_display_text.label.Label(
    LARGE_FONT,
    color=0x00FF00,  # Bright green
    text='--:--',
    x=4,
    y=10
)
main_group.append(time_label)

# Top right: AM/PM
ampm_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x00AA00,  # Dim green
    text='--',
    x=48,
    y=10
)
main_group.append(ampm_label)

# Middle left: Date
date_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x4080FF,  # Light blue
    text='--/--',
    x=2,
    y=20
)
main_group.append(date_label)

# Middle right: Outdoor temperature
outdoor_temp_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0xFFAA00,  # Orange
    text='Out:--F',
    x=34,
    y=20
)
main_group.append(outdoor_temp_label)

# Bottom left: Indoor temperature (placeholder)
indoor_temp_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0xFF4040,  # Coral red
    text='In:--F',
    x=2,
    y=30
)
main_group.append(indoor_temp_label)

# Bottom right: Indoor humidity (placeholder)
indoor_humid_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x40AAFF,  # Sky blue
    text='H:--%%',
    x=34,
    y=30
)
main_group.append(indoor_humid_label)

# === WEATHER OVERLAY (appears during weather updates) ===
# Line 1: Current condition
weather_condition_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0xFFFFFF,  # White
    text='',
    x=2,
    y=10
)
weather_group.append(weather_condition_label)

# Line 2: Current temp detail
weather_current_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0xFFAA00,  # Orange
    text='',
    x=2,
    y=19
)
weather_group.append(weather_current_label)

# Line 3: Tomorrow forecast
weather_tomorrow_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x40FF40,  # Light green
    text='',
    x=2,
    y=28
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
    
    # Update time display
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
    
    # Format time with proper spacing for centering
    time_text = f"{hour}:{minute:02d}"
    time_label.text = time_text
    ampm_label.text = am_pm
    
    # Update date
    date_label.text = f"{now.tm_mon}/{now.tm_mday}"
    
    # Update outdoor temperature
    if weather_data:
        outdoor_temp_label.text = f"Out:{weather_data['temp']:.0f}F"
    
    # Update indoor sensors (placeholder - replace with actual sensor readings)
    if indoor_temp is not None:
        indoor_temp_label.text = f"In:{indoor_temp:.0f}F"
    else:
        indoor_temp_label.text = "In:--F"
    
    if indoor_humidity is not None:
        indoor_humid_label.text = f"H:{indoor_humidity:.0f}%"
    else:
        indoor_humid_label.text = "H:--%"
    
    time.sleep(0.1)
