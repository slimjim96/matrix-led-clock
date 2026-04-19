# SPDX-FileCopyrightText: 2026 Test Clock for Matrix Portal
# SPDX-License-Identifier: MIT

"""
Simple animated clock test for Adafruit Matrix Portal
Tests display functionality with no internet required
Special effects trigger every 5 minutes
"""

import time
import board
import busio
import displayio
import math
from rtc import RTC
from adafruit_matrixportal.matrix import Matrix
from adafruit_bitmap_font import bitmap_font
import adafruit_display_text.label
import adafruit_lis3dh
import random

# CONFIGURATION
BITPLANES = 6
EFFECT_INTERVAL = 300  # 5 minutes in seconds

# Explicit positioning for 64x32 display
TIME_X = 2      # Time horizontal position
TIME_Y = 8      # Time vertical position  
DATE_X = 12     # Date horizontal position
DATE_Y = 22     # Date vertical position
AMPM_X = 42     # AM/PM horizontal position (closer to time)
AMPM_Y = 8      # AM/PM vertical position

# Initialize hardware
MATRIX = Matrix(bit_depth=BITPLANES)
DISPLAY = MATRIX.display

# Initialize accelerometer for auto-rotation
ACCEL = adafruit_lis3dh.LIS3DH_I2C(busio.I2C(board.SCL, board.SDA), address=0x19)
_ = ACCEL.acceleration
time.sleep(0.1)
DISPLAY.rotation = (int(((math.atan2(-ACCEL.acceleration.y,
                                     -ACCEL.acceleration.x) + math.pi) /
                         (math.pi * 2) + 0.875) * 4) % 4) * 90

# Load fonts
LARGE_FONT = bitmap_font.load_font('/fonts/helvB12.bdf')
SMALL_FONT = bitmap_font.load_font('/fonts/helvR10.bdf')
LARGE_FONT.load_glyphs('0123456789:')
SMALL_FONT.load_glyphs('0123456789:/.AMPSUN')

# Create display group
GROUP = displayio.Group()

# Time label (large) - subdued green
time_label = adafruit_display_text.label.Label(
    LARGE_FONT, 
    color=0x003300,  # Darker green
    text='12:00',
    x=TIME_X,
    y=16
)
GROUP.append(time_label)

# Date label (small) - subdued gray
date_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x404040,  # Darker gray
    text='1/18',
    x=16,
    y=28
)
GROUP.append(date_label)

# AM/PM indicator - subdued blue
ampm_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x004080,  # Darker blue
    text='AM',
    x=48,
    y=16
)
GROUP.append(ampm_label)

# Effect message label (initially hidden)
effect_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0xFF0000,
    text='',
    x=0,
    y=6
)
GROUP.append(effect_label)

DISPLAY.root_group = GROUP

print("Matrix Portal Clock Test Starting!")
print(f"Display: {DISPLAY.width}x{DISPLAY.height}")
print(f"Rotation: {DISPLAY.rotation}")
print("Effects trigger every 5 minutes")

# Helper function to format time
def format_time(t):
    hour = t.tm_hour
    minute = t.tm_min
    
    if hour == 0:
        hour_12 = 12
        ampm = 'AM'
    elif hour < 12:
        hour_12 = hour
        ampm = 'AM'
    elif hour == 12:
        hour_12 = 12
        ampm = 'PM'
    else:
        hour_12 = hour - 12
        ampm = 'PM'
    
    time_str = f'{hour_12}:{minute:02d}'
    return time_str,ampm

# Helper function for color cycling
def rainbow_color(position):
    """Generate subdued rainbow colors (0-255 position)"""
    # Reduce intensity to 40% for subdued colors
    if position < 85:
        return (int((255 - position * 3) * 0.4), int(position * 3 * 0.4), 0)
    elif position < 170:
        position -= 85
        return (0, int((255 - position * 3) * 0.4), int(position * 3 * 0.4))
    else:
        position -= 170
        return (int(position * 3 * 0.4), 0, int((255 - position * 3) * 0.4))

# Helper function to convert RGB tuple to 16-bit color
def rgb_to_color(rgb):
    r, g, b = rgb
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

# Special effects
def effect_rainbow_pulse(duration=5):
    """Rainbow color pulse effect"""
    print("Effect: Rainbow Pulse!")
    effect_label.text = 'RAINBOW'
    effect_label.color = 0x660066  # Subdued magenta
    
    start = time.monotonic()
    position = 0
    
    while time.monotonic() - start < duration:
        color = rainbow_color(position % 256)
        time_label.color = rgb_to_color(color)
        date_label.color = rgb_to_color(rainbow_color((position + 85) % 256))
        ampm_label.color = rgb_to_color(rainbow_color((position + 170) % 256))
        
        position += 5
        time.sleep(0.05)
    
    # Reset colors
    time_label.color = 0x003300  # Subdued green
    date_label.color = 0x404040  # Subdued gray
    ampm_label.color = 0x004080  # Subdued blue
    effect_label.text = ''

def effect_blink(duration=3):
    """Blink effect"""
    print("Effect: Blink!")
    effect_label.text = 'BLINK'
    effect_label.color = 0x666600  # Subdued yellow
    
    start = time.monotonic()
    
    while time.monotonic() - start < duration:
        time_label.color = 0x660000  # Subdued red
        time.sleep(0.3)
        time_label.color = 0x000000
        time.sleep(0.2)
    
    time_label.color = 0x006600  # Back to subdued green
    effect_label.text = ''

def effect_slide(duration=4):
    """Sliding text effect"""
    print("Effect: Slide!")
    effect_label.text = 'SLIDE'
    effect_label.color = 0x006666  # Subdued cyan
    
    original_x = time_label.x
    start = time.monotonic()
    
    # Slide out right (fixed for 64px display)
    for x in range(original_x, 74, 3):
        time_label.x = x
        time.sleep(0.03)
    
    # Slide in from left
    for x in range(-50, original_x + 1, 3):
        time_label.x = x
        time.sleep(0.03)
    
    time_label.x = original_x
    effect_label.text = ''

def effect_zoom(duration=3):
    """Zoom effect (change colors to simulate zoom)"""
    print("Effect: Zoom!")
    effect_label.text = 'ZOOM'
    effect_label.color = 0x664000  # Subdued orange
    
    # Subdued colors at 40% intensity
    colors = [0x660000, 0x664000, 0x666600, 0x006600, 0x006666, 0x000066, 0x660066]
    
    for _ in range(6):
        for color in colors:
            time_label.color = color
            time.sleep(0.15)
    
    time_label.color = 0x006600  # Back to subdued green
    effect_label.text = ''

def effect_matrix_rain(duration=5):
    """Matrix-style falling numbers"""
    print("Effect: Matrix Rain!")
    effect_label.text = 'MATRIX'
    effect_label.color = 0x006600  # Subdued green
    
    # Just alternate between green shades for time display
    start = time.monotonic()
    while time.monotonic() - start < duration:
        time_label.color = 0x006600
        date_label.color = 0x004000
        time.sleep(0.1)
        time_label.color = 0x005500
        date_label.color = 0x006600
        time.sleep(0.1)
    
    time_label.color = 0x006600  # Back to subdued green
    date_label.color = 0x404040  # Back to subdued gray
    effect_label.text = ''

# List of effects
EFFECTS = [
    effect_rainbow_pulse,
    effect_blink,
    effect_slide,
    effect_zoom,
    effect_matrix_rain
]

# Helper function for minute scroll message
def scroll_minute_message():
    """Fade in message every minute"""
    print("Minute message: You are awesome!")
    
    # Fade out time/date (dim the colors)
    for brightness in range(10, -1, -1):
        factor = brightness / 10.0
        time_label.color = int(0x003300 * factor) if brightness > 0 else 0x000000
        date_label.color = int(0x404040 * factor) if brightness > 0 else 0x000000
        ampm_label.color = int(0x004080 * factor) if brightness > 0 else 0x000000
        time.sleep(0.08)
    
    # Hide time/date completely
    time_label.text = ''
    date_label.text = ''
    ampm_label.text = ''
    
    # Show message centered
    effect_label.text = 'You are awesome!'
    effect_label.x = 2
    effect_label.y = 12
    
    # Fade in message (brighten the color)
    for brightness in range(11):
        factor = brightness / 10.0
        # Cyan gradient: 0x006666
        r = int(0x00 * factor)
        g = int(0x66 * factor)
        b = int(0x66 * factor)
        effect_label.color = (r << 16) | (g << 8) | b
        time.sleep(0.08)
    
    # Hold message for 2 seconds
    time.sleep(2)
    
    # Fade out message
    for brightness in range(10, -1, -1):
        factor = brightness / 10.0
        r = int(0x00 * factor)
        g = int(0x66 * factor)
        b = int(0x66 * factor)
        effect_label.color = (r << 16) | (g << 8) | b
        time.sleep(0.08)
    
    # Clear message
    effect_label.text = ''
    
    # Restore time/date text
    now = time.localtime()
    time_str, ampm = format_time(now)
    time_label.text = time_str
    date_label.text = f'{now.tm_mon}/{now.tm_mday}'
    ampm_label.text = ampm
    
    # Fade in time/date
    for brightness in range(11):
        factor = brightness / 10.0
        time_label.color = int(0x003300 * factor) if factor > 0 else 0x000000
        date_label.color = int(0x404040 * factor) if factor > 0 else 0x000000
        ampm_label.color = int(0x004080 * factor) if factor > 0 else 0x000000
        time.sleep(0.08)
    
    # Restore full colors
    time_label.color = 0x003300
    date_label.color = 0x404040
    ampm_label.color = 0x004080

# Main loop
last_effect_time = time.monotonic()
last_minute = -1
effect_index = 0

while True:
    # Get current time
    now = time.localtime()
    
    # Format and display time
    time_str, ampm = format_time(now)
    time_label.text = time_str
    ampm_label.text = ampm
    
    # Format and display date
    date_str = f'{now.tm_mon}/{now.tm_mday}'
    date_label.text = date_str
    
    # ===== EXPLICIT POSITIONING - ADJUST TIME_X, TIME_Y, etc. AT TOP OF FILE =====
    time_label.x = TIME_X
    time_label.y = TIME_Y
    
    date_label.x = DATE_X
    date_label.y = DATE_Y
    
    ampm_label.x = AMPM_X
    ampm_label.y = AMPM_Y
    
    effect_label.x = 2
    effect_label.y = 2
    
    # Log actual positions every second
    print(f'RENDER -> Time:"{time_str}" ({time_label.x},{time_label.y}) Date:"{date_str}" ({date_label.x},{date_label.y}) AM/PM:"{ampm}" ({ampm_label.x},{ampm_label.y})')
    
    # Scroll message every minute (when minute changes)
    if now.tm_min != last_minute:
        last_minute = now.tm_min
        scroll_minute_message()
    
    # Check if it's time for an effect
    current_time = time.monotonic()
    
    # Trigger effect every 5 minutes OR on the hour
    if (current_time - last_effect_time >= EFFECT_INTERVAL) or \
       (now.tm_min == 0 and now.tm_sec < 2):
        
        # Run random effect
        effect = EFFECTS[effect_index]
        effect()
        
        effect_index = (effect_index + 1) % len(EFFECTS)
        last_effect_time = current_time
        
        print(f"Time: {time_str} {ampm}")
    
    # Update every second
    time.sleep(1)
