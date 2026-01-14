import time
import machine
import network
import ntptime
import urequests
import gc9a01py as gc9a01
import vga1_16x32 as font

# Display Pins
TFT_SCK = 6
TFT_MOSI = 7
TFT_DC = 2
TFT_RST = 3
TFT_CS = 10
TFT_BL = 1

# Touch Pins
TOUCH_SDA = 4
TOUCH_SCL = 5
TOUCH_RST = 13
TOUCH_INT = 12

# CST816S Touch Driver
class CST816S:
    def __init__(self, i2c, rst_pin=None, int_pin=None):
        self.i2c = i2c
        self.addr = 0x15
        self.rst = machine.Pin(rst_pin, machine.Pin.OUT) if rst_pin else None
        self.int_pin = machine.Pin(int_pin, machine.Pin.IN) if int_pin else None
        
        if self.rst:
            self.rst.value(0)
            time.sleep_ms(10)
            self.rst.value(1)
            time.sleep_ms(50)
    
    def get_touch(self):
        try:
            data = self.i2c.readfrom_mem(self.addr, 0x00, 7)
            touch_points = data[2] & 0x0F
            
            if touch_points == 0:
                return None
            
            x = ((data[3] & 0x0F) << 8) | data[4]
            y = ((data[5] & 0x0F) << 8) | data[6]
            
            return {'x': x, 'y': y, 'points': touch_points}
        except:
            return None

# SPI for display
spi = machine.SPI(
    1,
    baudrate=40_000_000,
    polarity=0,
    phase=0,
    sck=machine.Pin(TFT_SCK),
    mosi=machine.Pin(TFT_MOSI)
)

# Display
display = gc9a01.GC9A01(
    spi,
    machine.Pin(TFT_DC, machine.Pin.OUT),
    machine.Pin(TFT_CS, machine.Pin.OUT),
    machine.Pin(TFT_RST, machine.Pin.OUT),
    machine.Pin(TFT_BL, machine.Pin.OUT),
    0
)

# I2C for touch
i2c = machine.I2C(0, sda=machine.Pin(TOUCH_SDA), scl=machine.Pin(TOUCH_SCL), freq=400000)

# Touch controller
try:
    touch = CST816S(i2c, rst_pin=TOUCH_RST, int_pin=TOUCH_INT)
    touch_enabled = True
except:
    touch_enabled = False
    print("Touch init failed")

# Colors
WHITE = gc9a01.WHITE
GREY = gc9a01.color565(180, 180, 180)
BLACK = gc9a01.BLACK
BLUE = gc9a01.color565(0, 150, 255)
YELLOW = gc9a01.color565(255, 255, 0)
RED = gc9a01.color565(255, 0, 0)
GREEN = gc9a01.color565(0, 255, 0)
ORANGE = gc9a01.color565(255, 165, 0)
DARK_BLUE = gc9a01.color565(0, 50, 100)

WIDTH = 240
HEIGHT = 240

# Mallow, Cork, Ireland coordinates
LAT = 52.1333
LON = -8.6333

wlan = None
weather_data = {"temp": "N/A", "desc": "Loading...", "wind": "0", "humidity": "0", "code": 0}
crypto_data = {"BTC": "Loading", "ETH": "Loading", "LTC": "Loading"}

# Screen structure: main_menu (vertical), sub_menu (horizontal)
main_menu = 0  # 0=time, 1=weather, 2=crypto, 3=search, 4=settings
sub_menu = 0   # submenu within each main menu
last_touch_x = None
last_touch_y = None

# Search/keyboard state
search_text = ""
keyboard_mode = "abc"  # "abc", "ABC", "123"
multitap_key = None
multitap_count = 0
multitap_time = 0

# Multitap letter mappings (like old Nokia phones)
multitap_letters = {
    "abc": ["a", "b", "c"],
    "def": ["d", "e", "f"],
    "ghi": ["g", "h", "i"],
    "jkl": ["j", "k", "l"],
    "mno": ["m", "n", "o"],
    "pqrs": ["p", "q", "r", "s"],
    "tuv": ["t", "u", "v"],
    "wxyz": ["w", "x", "y", "z"],
    "SPACE": [" "]
}

multitap_letters_upper = {
    "ABC": ["A", "B", "C"],
    "DEF": ["D", "E", "F"],
    "GHI": ["G", "H", "I"],
    "JKL": ["J", "K", "L"],
    "MNO": ["M", "N", "O"],
    "PQRS": ["P", "Q", "R", "S"],
    "TUV": ["T", "U", "V"],
    "WXYZ": ["W", "X", "Y", "Z"],
    "SPACE": [" "]
}

multitap_numbers = {
    "1": ["1"], "2": ["2"], "3": ["3"],
    "4": ["4"], "5": ["5"], "6": ["6"],
    "7": ["7"], "8": ["8"], "9": ["9"],
    "0": ["0"], ".": ["."], "@": ["@"]
}

def center_x(text, font_width=16):
    return (WIDTH - len(text) * font_width) // 2

# Swipe detection
def detect_swipe(touch_data):
    global last_touch_x, last_touch_y, main_menu, sub_menu
    
    if touch_data is None:
        last_touch_x = None
        last_touch_y = None
        return
    
    x = touch_data['x']
    y = touch_data['y']
    
    if last_touch_x is not None and last_touch_y is not None:
        delta_x = x - last_touch_x
        delta_y = y - last_touch_y
        
        # Vertical swipes = main menu navigation
        if abs(delta_y) > 50 and abs(delta_y) > abs(delta_x):
            if delta_y > 0:  # Swipe down
                main_menu = (main_menu + 1) % 5
            else:  # Swipe up
                main_menu = (main_menu - 1) % 5
            sub_menu = 0  # Reset submenu when changing main menu
            last_touch_x = None
            last_touch_y = None
            time.sleep_ms(300)
            return
        
        # Horizontal swipes = submenu navigation
        if abs(delta_x) > 40 and abs(delta_x) > abs(delta_y):
            # Get max submenus for current main menu
            max_subs = get_max_submenus(main_menu)
            if max_subs > 1:  # Only if there are submenus
                if delta_x < 0:  # Swipe left
                    sub_menu = (sub_menu + 1) % max_subs
                else:  # Swipe right
                    sub_menu = (sub_menu - 1) % max_subs
            last_touch_x = None
            last_touch_y = None
            time.sleep_ms(300)
            return
    
    last_touch_x = x
    last_touch_y = y

# Get max submenus for each main menu
def get_max_submenus(menu):
    if menu == 1:  # Weather has 2 submenus
        return 2
    return 1  # Others have just 1 screen

# Connect to WiFi
def connect_wifi():
    global wlan
    display.fill(BLACK)
    display.text(font, "WiFi...", center_x("WiFi..."), 110, WHITE)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect("SKYF30B4", "PWCSDPFU")
    
    timeout = 20
    while not wlan.isconnected() and timeout > 0:
        time.sleep(0.5)
        timeout -= 1
    
    return wlan.isconnected()

# Sync time with NTP
def sync_ntp():
    display.fill(BLACK)
    display.text(font, "Syncing...", center_x("Syncing..."), 110, WHITE)
    
    try:
        ntptime.settime()
        display.fill(BLACK)
        display.text(font, "Synced!", center_x("Synced!"), 110, WHITE)
        time.sleep(1)
        return True
    except:
        display.fill(BLACK)
        display.text(font, "Failed", center_x("Failed"), 110, RED)
        time.sleep(1)
        return False

# Get weather from Open-Meteo API
def get_weather():
    global weather_data
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}&current_weather=true&hourly=relative_humidity_2m".format(LAT, LON)
        response = urequests.get(url)
        data = response.json()
        response.close()
        
        temp = data["current_weather"]["temperature"]
        wind = data["current_weather"]["windspeed"]
        weather_code = data["current_weather"]["weathercode"]
        
        # Get humidity (first hourly value)
        humidity = data["hourly"]["relative_humidity_2m"][0] if "hourly" in data else 0
        
        # Weather descriptions based on WMO codes
        descriptions = {
            0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Cloudy",
            45: "Foggy", 48: "Foggy", 51: "Light Rain", 53: "Rain",
            55: "Heavy Rain", 61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
            71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 80: "Showers",
            81: "Showers", 82: "Heavy Showers", 95: "Thunderstorm"
        }
        
        desc = descriptions.get(weather_code, "Unknown")
        weather_data = {
            "temp": "{}C".format(int(temp)),
            "desc": desc,
            "wind": "{}km/h".format(int(wind)),
            "humidity": "{}%".format(int(humidity)),
            "code": weather_code
        }
        
    except Exception as e:
        print("Weather error:", e)
        weather_data = {"temp": "N/A", "desc": "Error", "wind": "N/A", "humidity": "N/A", "code": 0}

# Get crypto prices from Coinbase API (free, no API key needed)
def get_crypto():
    global crypto_data
    try:
        print("Fetching crypto prices...")
        
        # Get BTC in EUR
        response = urequests.get("https://api.coinbase.com/v2/prices/BTC-EUR/spot")
        btc_data = response.json()
        response.close()
        btc_price = float(btc_data["data"]["amount"])
        
        # Get ETH in EUR
        response = urequests.get("https://api.coinbase.com/v2/prices/ETH-EUR/spot")
        eth_data = response.json()
        response.close()
        eth_price = float(eth_data["data"]["amount"])
        
        # Get LTC in EUR
        response = urequests.get("https://api.coinbase.com/v2/prices/LTC-EUR/spot")
        ltc_data = response.json()
        response.close()
        ltc_price = float(ltc_data["data"]["amount"])
        
        # Format with euro symbol and cents
        crypto_data = {
            "BTC": "€{:.2f}".format(btc_price),
            "ETH": "€{:.2f}".format(eth_price),
            "LTC": "€{:.2f}".format(ltc_price)
        }
        print("Crypto data:", crypto_data)
        
    except Exception as e:
        print("Crypto error:", e)
        crypto_data = {"BTC": "Err", "ETH": "Err", "LTC": "Err"}

# Draw simple weather icons using only available methods
def draw_weather_icon(x, y, code):
    # Clear/Sunny - Simple sun with square center and lines
    if code in [0, 1]:
        display.fill_rect(x - 8, y - 8, 16, 16, YELLOW)
        display.line(x, y - 18, x, y - 12, YELLOW)
        display.line(x, y + 12, x, y + 18, YELLOW)
        display.line(x - 18, y, x - 12, y, YELLOW)
        display.line(x + 12, y, x + 18, y, YELLOW)
        display.line(x - 13, y - 13, x - 9, y - 9, YELLOW)
        display.line(x + 9, y - 9, x + 13, y - 13, YELLOW)
        display.line(x - 13, y + 9, x - 9, y + 13, YELLOW)
        display.line(x + 9, y + 9, x + 13, y + 13, YELLOW)
    elif code in [2]:
        display.fill_rect(x - 18, y - 10, 10, 10, YELLOW)
        display.fill_rect(x - 5, y, 20, 10, GREY)
        display.fill_rect(x, y - 5, 15, 10, GREY)
    elif code in [3, 45, 48]:
        display.fill_rect(x - 15, y, 20, 10, GREY)
        display.fill_rect(x - 5, y - 5, 15, 10, GREY)
        display.fill_rect(x + 5, y, 15, 10, GREY)
    elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        display.fill_rect(x - 15, y - 10, 20, 10, GREY)
        display.fill_rect(x - 5, y - 15, 15, 10, GREY)
        display.line(x - 10, y + 3, x - 10, y + 10, BLUE)
        display.line(x - 3, y + 5, x - 3, y + 12, BLUE)
        display.line(x + 4, y + 3, x + 4, y + 10, BLUE)
        display.line(x + 11, y + 5, x + 11, y + 12, BLUE)
    elif code in [71, 73, 75]:
        display.fill_rect(x - 15, y - 10, 20, 10, GREY)
        display.fill_rect(x - 5, y - 15, 15, 10, GREY)
        for sx in [-10, -2, 6]:
            sy = y + 6
            display.pixel(sx + x, sy, WHITE)
            display.pixel(sx + x - 1, sy, WHITE)
            display.pixel(sx + x + 1, sy, WHITE)
            display.pixel(sx + x, sy - 1, WHITE)
            display.pixel(sx + x, sy + 1, WHITE)
    elif code in [95, 96, 99]:
        display.fill_rect(x - 15, y - 10, 20, 10, DARK_BLUE)
        display.fill_rect(x - 5, y - 15, 15, 10, DARK_BLUE)
        display.line(x, y, x - 3, y + 6, YELLOW)
        display.line(x - 3, y + 6, x + 2, y + 6, YELLOW)
        display.line(x + 2, y + 6, x - 1, y + 12, YELLOW)

# TIME SCREEN
def draw_time_screen():
    t = time.localtime()
    datestr = "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])
    timestr = "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])
    
    display.text(font, "TIME", center_x("TIME"), 50, GREY)
    display.text(font, datestr, center_x(datestr), 95, GREY)
    display.text(font, timestr, center_x(timestr), 135, WHITE)
    
    # Navigation hints
    display.text(font, "v", center_x("v"), 200, BLUE)

# WEATHER SCREEN - Submenu 0 (Main weather)
def draw_weather_main():
    display.text(font, "WEATHER", center_x("WEATHER"), 30, GREY)
    draw_weather_icon(120, 90, weather_data["code"])
    display.text(font, weather_data["desc"], center_x(weather_data["desc"]), 130, BLUE)
    display.text(font, weather_data["temp"], center_x(weather_data["temp"]), 165, YELLOW)
    
    # Navigation hints
    display.text(font, "^", center_x("^"), 10, BLUE)
    display.text(font, "v", center_x("v"), 210, BLUE)
    display.text(font, "->", WIDTH - 40, 120, GREEN)

# WEATHER SCREEN - Submenu 1 (Details)
def draw_weather_details():
    display.text(font, "DETAILS", center_x("DETAILS"), 30, GREY)
    
    display.text(font, "Temp", 30, 75, GREY)
    display.text(font, weather_data["temp"], 150, 75, YELLOW)
    
    display.text(font, "Wind", 30, 110, GREY)
    display.text(font, weather_data["wind"], 150, 110, GREEN)
    
    display.text(font, "Humidity", 30, 145, GREY)
    display.text(font, weather_data["humidity"], 150, 145, BLUE)
    
    # Navigation hints
    display.text(font, "^", center_x("^"), 10, BLUE)
    display.text(font, "v", center_x("v"), 210, BLUE)
    display.text(font, "<-", 10, 120, GREEN)

# CRYPTO SCREEN
def draw_crypto_screen():
    display.text(font, "CRYPTO", center_x("CRYPTO"), 30, WHITE)
    
    display.text(font, "BTC", 20, 75, YELLOW)
    display.text(font, crypto_data["BTC"], 100, 75, YELLOW)
    
    display.text(font, "ETH", 20, 120, BLUE)
    display.text(font, crypto_data["ETH"], 100, 120, BLUE)
    
    display.text(font, "LTC", 20, 165, GREY)
    display.text(font, crypto_data["LTC"], 100, 165, GREY)
    
    # Navigation hints
    display.text(font, "^", center_x("^"), 10, BLUE)
    display.text(font, "v", center_x("v"), 210, BLUE)

# Handle keyboard touch
def handle_keyboard_touch(x, y):
    global search_text, keyboard_mode, multitap_key, multitap_count, multitap_time
    
    current_time = time.ticks_ms()
    
    # Get current key layout
    if keyboard_mode == "abc":
        keys = multitap_letters
    elif keyboard_mode == "ABC":
        keys = multitap_letters_upper
    else:
        keys = multitap_numbers
    
    key_list = list(keys.keys())
    
    # Keyboard grid layout (3x4)
    # Rows: 50, 90, 130, 170
    # Cols: 20, 90, 160
    button_w = 60
    button_h = 30
    
    row = -1
    col = -1
    
    if 50 <= y <= 80:
        row = 0
    elif 90 <= y <= 120:
        row = 1
    elif 130 <= y <= 160:
        row = 2
    elif 170 <= y <= 200:
        row = 3
    
    if 20 <= x <= 80:
        col = 0
    elif 90 <= x <= 150:
        col = 1
    elif 160 <= x <= 220:
        col = 2
    
    if row >= 0 and col >= 0:
        key_idx = row * 3 + col
        
        # Special buttons
        if key_idx == 9:  # Backspace
            if len(search_text) > 0:
                search_text = search_text[:-1]
            multitap_key = None
            return True
        elif key_idx == 10:  # Caps/Mode toggle
            if keyboard_mode == "abc":
                keyboard_mode = "ABC"
            elif keyboard_mode == "ABC":
                keyboard_mode = "123"
            else:
                keyboard_mode = "abc"
            multitap_key = None
            return True
        elif key_idx == 11:  # Search button
            # TODO: perform search
            multitap_key = None
            return True
        
        # Regular letter keys
        if key_idx < len(key_list):
            key_name = key_list[key_idx]
            
            # Multitap logic
            if multitap_key == key_name and (current_time - multitap_time) < 1000:
                # Same key pressed within 1 second - cycle through letters
                multitap_count = (multitap_count + 1) % len(keys[key_name])
                # Remove last character and add new one
                if len(search_text) > 0:
                    search_text = search_text[:-1]
            else:
                # New key or timeout - start fresh
                multitap_key = key_name
                multitap_count = 0
            
            search_text += keys[key_name][multitap_count]
            multitap_time = current_time
            return True
    
    return False

# SEARCH SCREEN
def draw_search_screen():
    display.text(font, "SEARCH", center_x("SEARCH"), 10, WHITE)
    
    # Search text input (truncate if too long)
    display_text = search_text[-10:] if len(search_text) > 10 else search_text
    display.text(font, display_text, 20, 30, YELLOW)
    display.hline(20, 45, 200, GREY)
    
    # Get current key layout
    if keyboard_mode == "abc":
        keys = list(multitap_letters.keys())
    elif keyboard_mode == "ABC":
        keys = list(multitap_letters_upper.keys())
    else:
        keys = list(multitap_numbers.keys())
    
    # Draw keyboard buttons (3x4 grid)
    y_pos = 50
    for row in range(4):
        x_pos = 20
        for col in range(3):
            idx = row * 3 + col
            
            # Special buttons on bottom row
            if idx == 9:
                display.rect(x_pos, y_pos, 60, 30, RED)
                display.text(font, "DEL", x_pos + 10, y_pos + 5, RED)
            elif idx == 10:
                display.rect(x_pos, y_pos, 60, 30, BLUE)
                mode_text = keyboard_mode if keyboard_mode != "123" else "123"
                display.text(font, mode_text[:3], x_pos + 10, y_pos + 5, BLUE)
            elif idx == 11:
                display.rect(x_pos, y_pos, 60, 30, GREEN)
                display.text(font, "GO", x_pos + 15, y_pos + 5, GREEN)
            elif idx < len(keys):
                display.rect(x_pos, y_pos, 60, 30, GREY)
                # Show first 4 chars of key label
                label = keys[idx][:4]
                display.text(font, label, x_pos + 5, y_pos + 5, WHITE)
            
            x_pos += 70
        y_pos += 40
    
    # Navigation hint
    display.text(font, "^", center_x("^"), 5, BLUE)
    display.text(font, "v", center_x("v"), 220, BLUE)
def draw_settings_screen():
    display.text(font, "SETTINGS", center_x("SETTINGS"), 80, WHITE)
    display.text(font, "(empty)", center_x("(empty)"), 120, GREY)
    display.text(font, "^", center_x("^"), 10, BLUE)

# Main draw function
def draw_screen():
    if main_menu == 0:
        draw_time_screen()
    elif main_menu == 1:
        if sub_menu == 0:
            draw_weather_main()
        else:
            draw_weather_details()
    elif main_menu == 2:
        draw_crypto_screen()
    elif main_menu == 3:
        draw_search_screen()
    else:
        draw_settings_screen()

# Setup
if connect_wifi():
    sync_ntp()
    get_weather()
    get_crypto()

# Main loop
counter = 0
last_main = -1
last_sub = -1

while True:
    # Check for touch input
    if touch_enabled:
        touch_data = touch.get_touch()
        
        # Handle keyboard touches on search screen
        if main_menu == 3 and touch_data:
            if handle_keyboard_touch(touch_data['x'], touch_data['y']):
                display.fill(BLACK)
                draw_search_screen()
        
        detect_swipe(touch_data)
    
    # Update weather every 10 minutes and crypto every 5 minutes
    if counter % 6000 == 0 and counter > 0:
        if wlan and wlan.isconnected():
            get_weather()
    
    if counter % 3000 == 0 and counter > 0:
        if wlan and wlan.isconnected():
            get_crypto()
    
    # Redraw when menu changes or time updates
    redraw = False
    if main_menu != last_main or sub_menu != last_sub:
        display.fill(BLACK)
        redraw = True
        last_main = main_menu
        last_sub = sub_menu
    elif main_menu == 0 and counter % 10 == 0:
        redraw = True
    
    if redraw:
        draw_screen()
    
    time.sleep(0.1)
    counter += 1