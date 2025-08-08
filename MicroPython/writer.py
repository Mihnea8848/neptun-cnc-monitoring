# NEPTUN S.A. CNC Monitor System
# Author: Mihnea Gîrbăcică, under MEH Studios Incorporated
# This software is protected by the Apache License 2004
# For any inquiries, contact @mihnea8848 on Discord or visit
# MEH Studios Incorp.'s website at mehstudios.net

from machine import Pin, I2C
import time

# Try to import SSD1306 driver
try:
    from ssd1306 import SSD1306_I2C
    DISPLAY_AVAILABLE = True
except ImportError:
    print("Warning: SSD1306 driver not available. Install ssd1306.py for display functionality")
    DISPLAY_AVAILABLE = False

class DisplayWriter:
    def __init__(self, scl_pin=1, sda_pin=0, width=128, height=64, i2c_addr=0x3C):
        """
        Initialize the display writer
        
        Args:
            scl_pin: GPIO pin for I2C clock (default: GPIO1)
            sda_pin: GPIO pin for I2C data (default: GPIO0)
            width: Display width in pixels (default: 128)
            height: Display height in pixels (default: 64)
            i2c_addr: I2C address of the display (default: 0x3C)
        """
        self.width = width
        self.height = height
        self.display = None
        self.font = None
        
        if not DISPLAY_AVAILABLE:
            print("Display driver not available")
            return
            
        try:
            # Initialize I2C
            self.i2c = I2C(0, scl=Pin(scl_pin), sda=Pin(sda_pin), freq=400000)
            
            # Scan for devices
            devices = self.i2c.scan()
            if i2c_addr not in devices:
                print(f"Display not found at address 0x{i2c_addr:02X}")
                print(f"Available I2C devices: {[hex(addr) for addr in devices]}")
                return
            
            # Initialize display
            self.display = SSD1306_I2C(width, height, self.i2c, addr=i2c_addr)
            
            # Load font
            try:
                from font5x9 import font5x9
                self.font = font5x9
                self.char_width = 6  # 5 pixels + 1 spacing
                self.char_height = 9
                print("Display initialized successfully with 5x9 font")
            except ImportError:
                print("Warning: font5x9.py not found, using basic font")
                self.char_width = 8
                self.char_height = 8
                
            # Clear display and show init message
            self.clear()
            self.write_text(0, 0, "Display Ready")
            self.show()
            time.sleep(1)
            
        except Exception as e:
            print(f"Display initialization failed: {e}")
            self.display = None
    
    def is_available(self):
        """Check if display is available and initialized"""
        return self.display is not None
    
    def clear(self):
        """Clear the display buffer"""
        if self.display:
            self.display.fill(0)
    
    def show(self):
        """Update the physical display with buffer contents"""
        if self.display:
            self.display.show()
    
    def draw_pixel(self, x, y, color=1):
        """Draw a single pixel"""
        if self.display and 0 <= x < self.width and 0 <= y < self.height:
            self.display.pixel(x, y, color)
    
    def draw_line(self, x1, y1, x2, y2, color=1):
        """Draw a line between two points"""
        if not self.display:
            return
            
        # Simple line drawing algorithm
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        
        x, y = x1, y1
        
        while True:
            self.draw_pixel(x, y, color)
            
            if x == x2 and y == y2:
                break
                
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
    
    def draw_hline(self, x, y, width, color=1):
        """Draw a horizontal line"""
        if self.display:
            self.display.hline(x, y, width, color)
    
    def draw_vline(self, x, y, height, color=1):
        """Draw a vertical line"""
        if self.display:
            self.display.vline(x, y, height, color)
    
    def draw_rect(self, x, y, width, height, color=1, fill=False):
        """Draw a rectangle"""
        if not self.display:
            return
            
        if fill:
            self.display.fill_rect(x, y, width, height, color)
        else:
            self.display.rect(x, y, width, height, color)
    
    def write_char(self, x, y, char, color=1):
        """Write a single character using custom font"""
        if not self.display or not self.font:
            # Fallback to built-in text if no custom font
            self.display.text(char, x, y, color)
            return
        
        # Get character code
        char_code = ord(char)
        if char_code < 32 or char_code > 126:
            char_code = 32  # Space for unknown characters
        
        # Calculate font index
        font_index = char_code - 32
        
        if font_index >= len(self.font):
            return
        
        # Get character bitmap
        char_data = self.font[font_index]
        
        # Draw character (5x9 bitmap)
        for row in range(9):
            if row < len(char_data):
                byte = char_data[row]
                for col in range(5):
                    if byte & (0x80 >> col):  # Check bit from left to right
                        pixel_x = x + col
                        pixel_y = y + row
                        if 0 <= pixel_x < self.width and 0 <= pixel_y < self.height:
                            self.draw_pixel(pixel_x, pixel_y, color)
    
    def write_text(self, x, y, text, color=1):
        """Write text string"""
        if not self.display:
            return
            
        if not self.font:
            # Use built-in text function if no custom font
            self.display.text(text, x, y, color)
            return
        
        # Use custom font
        current_x = x
        for char in str(text):
            if char == '\n':
                current_x = x
                y += self.char_height + 1
            else:
                self.write_char(current_x, y, char, color)
                current_x += self.char_width
                
                # Wrap to next line if text exceeds display width
                if current_x >= self.width - self.char_width:
                    current_x = x
                    y += self.char_height + 1
    
    def get_text_width(self, text):
        """Get the pixel width of text string"""
        return len(str(text)) * self.char_width
    
    def get_text_height(self):
        """Get the pixel height of a text line"""
        return self.char_height
    
    def center_text(self, y, text, color=1):
        """Write text centered horizontally"""
        text_width = self.get_text_width(text)
        x = (self.width - text_width) // 2
        self.write_text(x, y, text, color)
    
    def truncate_text(self, text, max_width):
        """Truncate text to fit within specified pixel width"""
        max_chars = max_width // self.char_width
        text = str(text)
        if len(text) <= max_chars:
            return text
        return text[:max_chars-3] + "..."

# Example usage and status display function
class CNCStatusDisplay:
    def __init__(self, scl_pin=1, sda_pin=0):
        """Initialize CNC status display"""
        self.writer = DisplayWriter(scl_pin, sda_pin)
        self.debug_y_start = 45  # Y position where debug area starts
        self.debug_lines = []
        self.max_debug_lines = 2  # Maximum debug lines to display
    
    def update_status(self, status="UNKNOWN", ssid="Not Connected", ip="0.0.0.0", debug_text=""):
        """Update the display with current status information"""
        if not self.writer.is_available():
            return
        
        # Clear display
        self.writer.clear()
        
        # Status (line 1)
        status_text = f"Status: {status}"
        self.writer.write_text(0, 0, status_text)
        
        # SSID (line 2)
        ssid_text = f"SSID: {self.writer.truncate_text(ssid, 128)}"
        self.writer.write_text(0, 10, ssid_text)
        
        # IP Address (line 3)
        ip_text = f"IP: {ip}"
        self.writer.write_text(0, 20, ip_text)
        
        # Draw separator line
        self.writer.draw_hline(0, 32, 128, 1)
        
        # Debug area label
        self.writer.write_text(0, 35, "Debug:")
        
        # Add debug text if provided
        if debug_text:
            self.add_debug(debug_text)
        
        # Display debug lines
        for i, line in enumerate(self.debug_lines[-self.max_debug_lines:]):
            y_pos = self.debug_y_start + (i * 9)
            if y_pos < 64:
                truncated_line = self.writer.truncate_text(line, 128)
                self.writer.write_text(0, y_pos, truncated_line)
        
        # Update display
        self.writer.show()
    
    def add_debug(self, text):
        """Add debug text line"""
        self.debug_lines.append(str(text))
        # Keep only recent debug lines
        if len(self.debug_lines) > 10:
            self.debug_lines = self.debug_lines[-10:]
    
    def clear_debug(self):
        """Clear debug text"""
        self.debug_lines = []

# Global display instance (to be used from main.py)
cnc_display = None

def init_display(scl_pin=1, sda_pin=0):
    """Initialize global display instance"""
    global cnc_display
    cnc_display = CNCStatusDisplay(scl_pin, sda_pin)
    return cnc_display

def update_display(status="UNKNOWN", ssid="Not Connected", ip="0.0.0.0", debug_text=""):
    """Update display with status (global function)"""
    global cnc_display
    if cnc_display:
        cnc_display.update_status(status, ssid, ip, debug_text)

def add_debug_line(text):
    """Add debug line to display (global function)"""
    global cnc_display
    if cnc_display:
        cnc_display.add_debug(text)