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

# Universal positioning offset - adjust these to move ALL elements
BASE_X_OFFSET = 0  # Horizontal starting point
BASE_Y_OFFSET = 0  # Vertical starting point

# Relative positions from base offset
TIME_X_OFFSET = 0
TIME_Y_OFFSET = 8
DATE_X_OFFSET = 16
DATE_Y_OFFSET = 22
AMPM_X_OFFSET = 0
AMPM_Y_OFFSET = 8
EFFECT_X_OFFSET = 0
EFFECT_Y_OFFSET = 2

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

# Time label (large)
time_label = adafruit_display_text.label.Label(
    LARGE_FONT, 
    color=0x006600,  # Darker green
    text='12:00',
    x=BASE_X_OFFSET + TIME_X_OFFSET,
    y=BASE_Y_OFFSET + TIME_Y_OFFSET
)
GROUP.append(time_label)

# Date label (small)
date_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x404040,  # Darker gray
    text='1/18',
    x=BASE_X_OFFSET + DATE_X_OFFSET,
    y=BASE_Y_OFFSET + DATE_Y_OFFSET
)
GROUP.append(date_label)

# AM/PM indicator
ampm_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0x004080,  # Darker blue
    text='AM',
    x=BASE_X_OFFSET + AMPM_X_OFFSET,
    y=BASE_Y_OFFSET + AMPM_Y_OFFSET
)
GROUP.append(ampm_label)

# Effect message label (initially hidden)
effect_label = adafruit_display_text.label.Label(
    SMALL_FONT,
    color=0xFF0000,
    text='',
    x=BASE_X_OFFSET + EFFECT_X_OFFSET,
    y=BASE_Y_OFFSET + EFFECT_Y_OFFSET
)
GROUP.append(effect_label)

DISPLAY.root_group = GROUP

print("Matrix Portal Clock Test Starting!")
print(f"Display: {DISPLAY.width}x{DISPLAY.height}")
print(f"Rotation: {DISPLAY.rotation}")
print(f"Base Offset: X={BASE_X_OFFSET}, Y={BASE_Y_OFFSET}")
print(f"Time position: X={BASE_X_OFFSET + TIME_X_OFFSET}, Y={BASE_Y_OFFSET + TIME_Y_OFFSET}")
print(f"Date position: X={BASE_X_OFFSET + DATE_X_OFFSET}, Y={BASE_Y_OFFSET + DATE_Y_OFFSET}")
print(f"AM/PM position: X={BASE_X_OFFSET + AMPM_X_OFFSET}, Y={BASE_Y_OFFSET + AMPM_Y_OFFSET}")
print("Effects trigger every 5 minutes")
print("64x32 LED Matrix - P4 Display")

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
    return time_str, ampm

# Helper function for color cycling
def rainbow_color(position):
    """Generate rainbow colors (0-255 position)"""
    if position < 85:
        return (255 - position * 3, position * 3, 0)
    elif position < 170:
        position -= 85
        return (0, 255 - position * 3, position * 3)
    else:
        position -= 170
        return (position * 3, 0, 255 - position * 3)

# Helper function to convert RGB tuple to 16-bit color
def rgb_to_color(rgb):
    r, g, b = rgb
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

# Special effects
def effect_rainbow_pulse(duration=5):
    """Rainbow color pulse effect"""
    print("Effect: Rainbow Pulse!")
    effect_label.text = 'RAINBOW'
    effect_label.color = 0xFF00FF
    
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
    time_label.color = 0x00FF00
    date_label.color = 0x808080
    ampm_label.color = 0x0080FF
    effect_label.text = ''

def effect_blink(duration=3):
    """Blink effect"""
    print("Effect: Blink!")
    effect_label.text = 'BLINK'
    effect_label.color = 0xFFFF00
    
    start = time.monotonic()
    
    while time.monotonic() - start < duration:
        time_label.color = 0xFF0000
        time.sleep(0.3)
        time_label.color = 0x000000
        time.sleep(0.2)
    
    time_label.color = 0x00FF00
    effect_label.text = ''

def effect_slide(duration=4):
    """Sliding text effect"""
    print("Effect: Slide!")
    effect_label.text = 'SLIDE'
    effect_label.color = 0x00FFFF
    
    original_x = time_label.x
    start = time.monotonic()
    
    # Slide out right (fixed value for 64px width display)
    for x in range(original_x, 74, 3):  # 64 + 10 = 74
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
    effect_label.color = 0xFF8000
    
    colors = [0xFF0000, 0xFF8000, 0xFFFF00, 0x00FF00, 0x00FFFF, 0x0000FF, 0xFF00FF]
    
    for _ in range(6):
        for color in colors:
            time_label.color = color
            time.sleep(0.15)
    
    time_label.color = 0x00FF00
    effect_label.text = ''

def effect_matrix_rain(duration=5):
    """Matrix-style falling numbers"""
    print("Effect: Matrix Rain!")
    effect_label.text = 'MATRIX'
    effect_label.color = 0x00FF00
    
    # Just alternate between green shades for time display
    start = time.monotonic()
    while time.monotonic() - start < duration:
        time_label.color = 0x00FF00
        date_label.color = 0x008000
        time.sleep(0.1)
        time_label.color = 0x00AA00
        date_label.color = 0x00FF00
        time.sleep(0.1)
    
    time_label.color = 0x00FF00
    date_label.color = 0x808080
    effect_label.text = ''

# List of effects
EFFECTS = [
    effect_rainbow_pulse,
    effect_blink,
    effect_slide,
    effect_zoom,
    effect_matrix_rain
]

# Main loop
last_effect_time = time.monotonic()
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
    
    # ===== FINAL RENDERING POSITIONS - THIS IS WHERE TEXT APPEARS ON DISPLAY =====
    time_label.x = BASE_X_OFFSET + TIME_X_OFFSET
    time_label.y = BASE_Y_OFFSET + TIME_Y_OFFSET
    
    date_label.x = BASE_X_OFFSET + DATE_X_OFFSET
    date_label.y = BASE_Y_OFFSET + DATE_Y_OFFSET
    
    ampm_label.x = BASE_X_OFFSET + AMPM_X_OFFSET
    ampm_label.y = BASE_Y_OFFSET + AMPM_Y_OFFSET
    
    effect_label.x = BASE_X_OFFSET + EFFECT_X_OFFSET
    effect_label.y = BASE_Y_OFFSET + EFFECT_Y_OFFSET
    
    # Log actual rendered positions every second
    print(f'RENDER -> Time: "{time_str}" at ({time_label.x},{time_label.y}) | Date: "{date_str}" at ({date_label.x},{date_label.y}) | AM/PM: "{ampm}" at ({ampm_label.x},{ampm_label.y})')
    
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
