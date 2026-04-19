"""
Test script for Moon API connection
Run this on your PC to verify the API is accessible
"""

import requests
from datetime import datetime
import json

# Read settings from settings.toml
def read_setting(key):
    try:
        with open('settings.toml', 'r') as f:
            for line in f:
                if line.strip().startswith(key):
                    # Extract value between quotes
                    value = line.split('=')[1].strip()
                    return value.strip('"').strip("'")
    except Exception as e:
        print(f"Error reading settings: {e}")
    return None

# Get settings
LATITUDE = read_setting('latitude')
LONGITUDE = read_setting('longitude')

print("=" * 60)
print("Moon API Connection Test")
print("=" * 60)
print(f"Latitude: {LATITUDE}")
print(f"Longitude: {LONGITUDE}")
print()

if not LATITUDE or not LONGITUDE:
    print("ERROR: Could not read latitude/longitude from settings.toml")
    exit(1)

# Build URL (same as CircuitPython code)
today = datetime.now()
utc_offset = "-05:00"  # Eastern Time (adjust if needed)
url = (f'https://api.met.no/weatherapi/sunrise/3.0/moon?'
       f'lat={LATITUDE}&lon={LONGITUDE}&'
       f'date={today.year}-{today.month:02d}-{today.day:02d}&'
       f'offset={utc_offset}')

print(f"Testing URL: {url}")
print()

# Headers required by MET Norway API
headers = {
    "User-Agent": "AdafruitMoonClock/1.1 support@adafruit.com"
}

# Try to fetch data
print("Attempting to fetch moon data...")
try:
    response = requests.get(url, headers=headers, timeout=30)
    
    print(f"Response Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print()
    
    if response.status_code == 200:
        print("✓ SUCCESS! API is accessible")
        print()
        
        # Parse JSON
        data = response.json()
        print("Moon Data Retrieved:")
        print(json.dumps(data, indent=2))
        
        # Extract key info
        if 'properties' in data:
            props = data['properties']
            if 'moonphase' in props:
                phase = props['moonphase']
                age = float(phase) / 360
                print()
                print(f"Moon Phase Angle: {phase}°")
                print(f"Moon Age: {age:.3f} (0=new, 0.5=full, 1=new)")
                
                if 'moonrise' in props and props['moonrise']['time']:
                    print(f"Moonrise: {props['moonrise']['time']}")
                if 'moonset' in props and props['moonset']['time']:
                    print(f"Moonset: {props['moonset']['time']}")
        
        print()
        print("✓ The API is working correctly!")
        print("The issue is likely with your CircuitPython/MatrixPortal setup.")
        
    else:
        print(f"✗ ERROR: Server returned status {response.status_code}")
        print(f"Response: {response.text}")
        
except requests.exceptions.Timeout:
    print("✗ ERROR: Request timed out")
    print("This suggests network or firewall issues")
    
except requests.exceptions.SSLError as e:
    print("✗ ERROR: SSL/TLS Error")
    print(f"Details: {e}")
    print("This suggests SSL certificate issues")
    
except requests.exceptions.ConnectionError as e:
    print("✗ ERROR: Connection Error")
    print(f"Details: {e}")
    print("Check your internet connection")
    
except Exception as e:
    print(f"✗ ERROR: {type(e).__name__}: {e}")

print()
print("=" * 60)
