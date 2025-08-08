# NEPTUN S.A. CNC Monitor System
# Author: Mihnea Gîrbăcică, under MEH Studios Incorporated
# This software is protected by the Apache License 2004
# For any inquiries, contact @mihnea8848 on Discord or visit
# MEH Studios Incorp.'s website at mehstudios.net

import network
import socket
import json
import time
import machine
from machine import Pin, Timer
import gc
import ubinascii

# MQTT imports
try:
    from umqtt.simple import MQTTClient
    MQTT_AVAILABLE = True
except ImportError:
    print("Warning: MQTT not available.")
    MQTT_AVAILABLE = False

# Display imports
try:
    from writer import init_display, update_display, add_debug_line
    DISPLAY_AVAILABLE = True
    print("Display modules loaded successfully")
except ImportError as e:
    print(f"Warning: Display not available: {e}")
    DISPLAY_AVAILABLE = False

# --- Configuration ---
STATUS_PIN = Pin(21, Pin.IN, Pin.PULL_DOWN)
DISPLAY_SCL_PIN = 5
DISPLAY_SDA_PIN = 4
FALLBACK_SSID = "Neptun-Monitor-AP"
FALLBACK_PASS = "apneptun"

# --- Configuration (first time config) ---
current_config = {
    'ssid': "nepiot",
    'password': 'iotneptun',
    'ip': '',
    'mqtt_broker': '10.48.48.166',
    'mqtt_port': 1883,
    'mqtt_topic': 'cnc1/status',
    'mqtt_interval': 5
}
wlan = None; server_socket = None; mqtt_client = None; mqtt_timer = None; last_status = None; display = None; current_mode = "STA"; dns_server = None

class DNSServer:
    def __init__(self, ip_address):
        self.ip_address = ip_address; self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.udp_socket.setblocking(False); self.udp_socket.bind(('', 53)); print("DNS server started")
    def process_requests(self):
        try:
            data, addr = self.udp_socket.recvfrom(1024)
            if data:
                packet = data; ip_parts = [int(p) for p in self.ip_address.split('.')]; ip_bytes = bytes(ip_parts)
                response = (packet[:2] + b'\x81\x80' + packet[4:6] + packet[4:6] + b'\x00\x00\x00\x00' + packet[12:] + b'\xc0\x0c' + b'\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04' + ip_bytes)
                self.udp_socket.sendto(response, addr)
        except OSError as e:
            if e.args[0] != 11: print(f"DNS server error: {e}")
    def stop(self):
        if self.udp_socket: self.udp_socket.close(); print("DNS server stopped")

def load_config():
    global current_config
    try:
        with open('config.json', 'r') as f: current_config.update(json.load(f)); print("Configuration loaded")
    except:
        print("No config file found, using defaults")

def save_config():
    try:
        with open('config.json', 'w') as f: json.dump(current_config, f); print("Configuration saved")
    except Exception as e:
        print(f"Error saving config: {e}")

def get_cnc_status():
    return "ONLINE" if STATUS_PIN.value() == 1 else "OFFLINE"

def display_connecting_info(target_ssid, retries_left):
    if not DISPLAY_AVAILABLE or not display: return
    try:
        writer = display.writer; writer.clear()
        writer.write_text(0, 0, "Status: Connecting...")
        writer.write_text(0, 20, f"Target: {writer.truncate_text(target_ssid, 128)}")
        writer.write_text(0, 40, f"Retries left: {retries_left}")
        writer.show()
    except Exception as e: print(f"Connecting display error: {e}")

def display_ap_fallback_info():
    if not DISPLAY_AVAILABLE or not display: return
    try:
        writer = display.writer; writer.clear()
        writer.center_text(0, ">> AP FALLBACK <<")
        writer.write_text(0, 15, f"SSID: {FALLBACK_SSID}")
        writer.write_text(0, 25, f"Pass: {FALLBACK_PASS}")
        writer.write_text(0, 40, "Please connect and")
        writer.write_text(0, 50, "config new SSID.")
        writer.show()
    except Exception as e: print(f"AP display error: {e}")

def update_display_info(t=None):
    if not DISPLAY_AVAILABLE or not display or current_mode == "AP": return
    try:
        status = get_cnc_status(); ssid = current_config.get('ssid', "Not Set")
        if wlan and wlan.isconnected(): ip = wlan.ifconfig()[0]; ssid = current_config['ssid']
        else: ip = "Connecting..."; ssid = current_config['ssid']
        update_display(status, ssid, ip)
    except Exception as e: print(f"Display update error: {e}")

def setup_ap_mode():
    global wlan, current_mode, dns_server
    current_mode = "AP"; wlan = network.WLAN(network.AP_IF); wlan.active(True)
    wlan.config(essid=FALLBACK_SSID, password=FALLBACK_PASS, authmode=network.AUTH_WPA_WPA2_PSK)
    ap_ip = wlan.ifconfig()[0]; print(f"AP '{FALLBACK_SSID}' started at {ap_ip}")
    dns_server = DNSServer(ap_ip)
    if DISPLAY_AVAILABLE: display_ap_fallback_info()
    return True

def connect_wifi():
    global wlan, current_mode
    current_mode = "STA";
    if not current_config.get('ssid') or not current_config.get('password'): return False
    wlan = network.WLAN(network.STA_IF); wlan.active(True)
    wlan.connect(current_config['ssid'], current_config['password'])
    timeout = 20
    while not wlan.isconnected() and timeout > 0:
        display_connecting_info(current_config['ssid'], timeout); print(f"Connecting... ({timeout})")
        time.sleep(1); timeout -= 1
    if wlan.isconnected():
        print(f"\nConnected! IP: {wlan.ifconfig()[0]}"); return True
    else:
        print(f"\nFailed to connect"); return False

def connect_mqtt():
    global mqtt_client
    if not MQTT_AVAILABLE or not current_config.get('mqtt_broker'):
        print("[MQTT LOG] Client not available or broker not configured.")
        return False
    try:
        client_id = f"esp32-c3-cnc-{ubinascii.hexlify(machine.unique_id()).decode()}"
        mqtt_broker = current_config['mqtt_broker']
        mqtt_port = current_config.get('mqtt_port')
        mqtt_client = MQTTClient(client_id, mqtt_broker, port=mqtt_port)
        add_debug_line("MQTT Connecting...")
        print(f"[MQTT LOG] Attempting to connect to broker at {mqtt_broker}:{mqtt_port}")
        mqtt_client.connect()
        print(f"[MQTT LOG] Successfully connected to MQTT broker.")
        add_debug_line("MQTT Connected")
        return True
    except Exception as e:
        print(f"[MQTT LOG] FATAL: MQTT connection failed: {e}")
        add_debug_line("MQTT Conn Fail")
        mqtt_client = None
        return False

def publish_mqtt_status(timer=None):
    global mqtt_client, last_status
    if not mqtt_client: return
    try:
        current_status_str = get_cnc_status()
        if current_status_str != last_status or timer is not None:
            cycle_value = 1 if current_status_str == "ONLINE" else 0
            # Manually construct the JSON string to guarantee order
            payload = f'{{"cycle":{cycle_value},"L1":0,"L2":0,"L3":0}}'
            topic = current_config['mqtt_topic']
            print(f"[MQTT LOG] Publishing to topic '{topic}': {payload}")
            mqtt_client.publish(topic.encode('utf-8'), payload.encode('utf-8'))
            print("[MQTT LOG] Publish successful.")
            add_debug_line(f"MQTT Pub: {current_status_str}")
            last_status = current_status_str
    except Exception as e:
        print(f"[MQTT LOG] ERROR: MQTT publish failed: {e}"); add_debug_line("MQTT Pub Fail")
        mqtt_client = None

def start_mqtt_timer():
    global mqtt_timer
    if mqtt_timer: mqtt_timer.deinit()
    interval = current_config.get('mqtt_interval', 0)
    if interval > 0 and current_config.get('mqtt_broker'):
        interval_ms = interval * 1000
        for timer_id in [2, 3, 0, 1]:
            try:
                mqtt_timer = Timer(timer_id); mqtt_timer.init(period=interval_ms, mode=Timer.PERIODIC, callback=publish_mqtt_status)
                print(f"MQTT timer started with {interval}s interval"); add_debug_line(f"MQTT Timer: {interval}s"); return
            except: mqtt_timer = None
        print("Warning: Could not start MQTT timer"); add_debug_line("MQTT Timer Fail")

def parse_form_data(data):
    form_data = {}; pairs = data.split('&')
    for pair in pairs:
        if '=' in pair: key, value = pair.split('=', 1); value = value.replace('+', ' ').replace('%20', ' '); form_data[key] = value
    return form_data

def check_ssid_visible(target_ssid):
    max_retries = 10; scan_delay_s = 1
    print(f"Scanning for SSID: '{target_ssid}'..."); sta_if = network.WLAN(network.STA_IF); sta_if.active(True)
    for attempt in range(max_retries):
        try:
            print(f"  Scan attempt {attempt + 1}/{max_retries}...")
            networks = sta_if.scan()
            for net in networks:
                if net[0].decode('utf-8') == target_ssid:
                    print(f"Success! Found '{target_ssid}'");
                    if current_mode == "AP": sta_if.active(False)
                    return True
            time.sleep(scan_delay_s)
        except Exception as e:
            print(f"  Error during scan: {e}"); time.sleep(scan_delay_s)
    print(f"Failed to find SSID '{target_ssid}' after {max_retries} attempts.")
    if current_mode == "AP": sta_if.active(False)
    return False

def handle_request(client_socket):
    try:
        request = client_socket.recv(1024).decode('utf-8')
        if not request: return
        
        # Defensive parsing
        try:
            request_line = request.split('\n')[0]
            method, path, _ = request_line.split(' ', 2)
        except (ValueError, IndexError):
            # If request is malformed, close the connection and exit
            return

        print(f"Request: {method} {path}")
        
        # Known API/data paths
        known_paths = ["/", "/status", "/scan", "/config"]
        is_known_path = False
        for p in known_paths:
            if path == p or path.startswith(p + "?"):
                is_known_path = True
                break
        
        # Captive portal redirect logic
        if current_mode == "AP" and not is_known_path:
            redirect_url = f"http://{wlan.ifconfig()[0]}"
            print(f"Captive Portal Triggered for path '{path}'. Redirecting to {redirect_url}")
            client_socket.send(f"HTTP/1.1 302 Found\r\nLocation: {redirect_url}\r\n\r\n".encode('utf-8'))
            return
        
        # Handle GET requests for our known paths
        if method == "GET":
            if path.startswith("/scan"):
                query = path.split("?", 1)[1] if "?" in path else ""
                params = parse_form_data(query)
                target_ssid = params.get('ssid', '')
                ssid_is_visible = check_ssid_visible(target_ssid)
                response_json = json.dumps({'found': ssid_is_visible})
                client_socket.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n'.encode('utf-8'))
                client_socket.send(response_json.encode('utf-8'))

            elif path == "/config":
                safe_config = current_config.copy()
                safe_config['password'] = '' # Never send password to client
                response_json = json.dumps(safe_config)
                client_socket.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n'.encode('utf-8'))
                client_socket.send(response_json.encode('utf-8'))

            elif path == "/status":
                response_data = {"status": get_cnc_status(), "gpio_value": STATUS_PIN.value()}
                response = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{json.dumps(response_data)}"
                client_socket.send(response.encode('utf-8'))

            elif path == "/" or path.startswith("/?"):
                if "?" in path: # This is a form submission to save data
                    query = path.split("?", 1)[1]
                    form_data = parse_form_data(query)
                    for key, value in form_data.items():
                        if key in current_config:
                            if key == 'password' and not value.strip(): continue
                            if value.strip() or key in ['ip', 'mqtt_broker']:
                                if key in ['mqtt_port', 'mqtt_interval']:
                                    try: current_config[key] = int(value)
                                    except: pass
                                else: current_config[key] = value.strip()
                    save_config()
                    response = f"HTTP/1.1 200 OK\r\n\r\n<html><body><h1>Configuration Saved!</h1><p>Device will reboot...</p></body></html>"
                    client_socket.send(response.encode('utf-8'))
                    time.sleep(3)
                    machine.reset()
                    return
                else: # This is a request for the main page
                    client_socket.send('HTTP/1.1 200 OK\r\nContent-type: text/html\r\n\r\n'.encode('utf-8'))
                    with open('index.html', 'rb') as f:
                        while True:
                            chunk = f.read(512)
                            if not chunk: break
                            client_socket.send(chunk)
            
            else:
                client_socket.send("HTTP/1.1 404 Not Found\r\n\r\n<h1>404</h1>".encode('utf-8'))

    except Exception as e:
        print(f"Error handling request: {e}")
    finally:
        if 'client_socket' in locals() and client_socket:
            client_socket.close()

def start_server():
    global server_socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM); server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('', 80)); server_socket.listen(5); server_socket.setblocking(False)
    print("Web server started")
    
    display_timer = None
    if current_mode == "STA":
        try:
            for timer_id in [1, 0, 2, 3]:
                try: display_timer = Timer(timer_id); display_timer.init(period=5000, mode=Timer.PERIODIC, callback=update_display_info); break
                except: display_timer = None
        except: print("Could not start display update timer")

    while True:
        try:
            if current_mode == "STA":
                if not wlan.isconnected():
                    print("Wi-Fi disconnected. Reconnecting..."); add_debug_line("WiFi Lost...")
                    if not connect_wifi():
                        print("Reconnect failed. Rebooting to AP mode."); add_debug_line("Reconnect failed")
                        time.sleep(3); machine.reset()
                    else:
                        print("Reconnected successfully!"); add_debug_line("WiFi OK!")
                        if current_config.get('mqtt_broker'): connect_mqtt()
                
                if current_config.get('mqtt_broker') and mqtt_client is None:
                    print("[MQTT LOG] MQTT client is disconnected. Attempting to reconnect...")
                    connect_mqtt()

            client_socket = None
            try:
                client_socket, addr = server_socket.accept()
                if client_socket: handle_request(client_socket)
            except OSError as e:
                if e.args[0] != errno.EAGAIN: print(f"Server accept error: {e}")
            except Exception as e: print(f"Error in web server loop: {e}")
            finally:
                if client_socket: client_socket.close()
            
            if current_mode == "AP" and dns_server: dns_server.process_requests()
            gc.collect()
            time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nShutting down server...")
            break
        except Exception as e:
            print("--- FATAL ERROR IN MAIN LOOP ---"); print(f"Error: {e}"); print("Rebooting in 10 seconds..."); time.sleep(10); machine.reset()
    
    if display_timer: display_timer.deinit()
    if server_socket: server_socket.close()
    if dns_server: dns_server.stop()

def main():
    global display
    if DISPLAY_AVAILABLE:
        try:
            display = init_display(DISPLAY_SCL_PIN, DISPLAY_SDA_PIN)
        except: display = None
    
    load_config()
    wifi_connected = False
    if current_config.get('ssid') and current_config.get('password'):
        wifi_connected = connect_wifi()
    if not wifi_connected:
        setup_ap_mode()
    else:
        current_mode = "STA"
        if current_config.get('mqtt_broker'):
            if connect_mqtt():
                start_mqtt_timer()
                publish_mqtt_status(timer=True)
        update_display(get_cnc_status(), current_config.get('ssid'), wlan.ifconfig()[0])
    
    print("\nSystem ready!")
    start_server()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram interrupted.")
        if dns_server: dns_server.stop()
    except Exception as e:
        print(f"Fatal error: {e}")
        time.sleep(5); machine.reset()