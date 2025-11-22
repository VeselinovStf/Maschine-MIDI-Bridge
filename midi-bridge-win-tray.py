import mido
import threading
import time
import re
import os
import argparse
import json
from collections import defaultdict
import sys
import subprocess
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw
import traceback
import rtmidi
import mido.backends.rtmidi

# ---------------------------------------------------------------------
# Args & Globals
# ---------------------------------------------------------------------
DEBUG = False  # will be overwritten by config
config = None
maschine_in_port = None
melodics_in_port = None
melodics_out_port = None
maschine_out_port = None
error_message = None
threads = []  # Track running threads
LOG_FILE = "midi-bridge-win-tray.log"

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
def log_debug(*args):
    """Append debug messages to a log file."""
    if DEBUG:
        log(args)

def log(*args):
    with open(LOG_FILE, "a") as f:
        message = " ".join(str(a) for a in args)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] {message}\n")

def load_config(path='config.json'):
    with open(path, 'r') as f:
        cfg = json.load(f)
    global DEBUG
    DEBUG = cfg.get("DEBUG", False)  # get debug from config
    return cfg

# ---------------------------------------------------------------------
# Tray UI
# ---------------------------------------------------------------------
def create_image():
    img = Image.new('RGB', (64, 64), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 48, 48), fill='white')
    return img

# ---------------------------------------------------------------------
# Tray UI (updated with Stop & Show Log)
# ---------------------------------------------------------------------
def setup_tray():
    icon_ref = {"icon": None}  # Mutable ref for access inside callbacks
    listening = {"running": False, "mode": None}

    def on_quit(icon, item):
        # Stop all threads by clearing thread list
        for t in threads:
            if t.is_alive():
                # Threads are daemon, they will exit when main exits
                pass
        icon.stop()
        sys.exit()

    def on_show_error(icon, item):
        from tkinter import messagebox, Tk
        root = Tk()
        root.withdraw()
        messagebox.showerror("MIDI Port Error", error_message or "No error.")
        root.destroy()

    def on_show_log(icon, item):
        import os
        if os.path.exists(LOG_FILE):
            if sys.platform == "win32":
                os.startfile(LOG_FILE)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", LOG_FILE])
            else:
                subprocess.Popen(["xdg-open", LOG_FILE])
        else:
            from tkinter import messagebox, Tk
            root = Tk()
            root.withdraw()
            messagebox.showinfo("Log File", "Log file does not exist yet.")
            root.destroy()

    def start_normal(icon, item):
        if not listening["running"]:
            listening["running"] = True
            listening["mode"] = "Normal"
            start_listening(normal_mode=True)
            update_menu(icon)
    
    def start_dark(icon, item):
        if not listening["running"]:
            listening["running"] = True
            listening["mode"] = "Dark"
            start_listening(normal_mode=False)
            update_menu(icon)

    def stop_listening(icon, item):
        listening["running"] = False
        listening["mode"] = None
        # Threads are daemon, so they will stop when program exits
        update_menu(icon)

    def update_menu(icon):
        items = []

        # If not running, show mode selectors
        if not listening["running"]:
            items += [
                MenuItem("▶ Start Normal", start_normal),
                MenuItem("🌑 Start Dark", start_dark),
            ]
        else:
            # Show only the stop option for the currently running mode
            items.append(MenuItem(f"⏸ Stop ({listening['mode']} Mode)", stop_listening))

        # Always show log and exit
        items.append(MenuItem("📄 Show Log", on_show_log))
        if error_message:
            items.append(MenuItem("⚠ Show Port Error", on_show_error))
        items.append(MenuItem("Exit", on_quit))

        icon.menu = Menu(*items)
        icon.update_menu()

    icon = Icon("MidiBridge_v2_1", create_image())
    icon_ref["icon"] = icon
    update_menu(icon)
    icon.run()

# ---------------------------------------------------------------------
# Find MIDI ports
# ---------------------------------------------------------------------
def find_ports(retry_interval=5):
    global error_message
    patterns = config['patterns']

    while True:
        input_ports = mido.get_input_names()
        output_ports = mido.get_output_names()

        log("Available input ports:", input_ports)
        log("Available output ports:", output_ports)

        # Match ports
        maschine_in = next((p for p in input_ports if re.match(patterns['maschine_in_port'], p)), None)
        melodics_in = next((p for p in output_ports if re.match(patterns['melodics_in_port'], p)), None)
        melodics_out = next((p for p in input_ports if re.match(patterns['melodics_out_port'], p)), None)
        maschine_out = next((p for p in output_ports if re.match(patterns['maschine_out_port'], p)), None)

        missing = [name for name, val in zip(
            ['maschine_in_port', 'melodics_in_port', 'melodics_out_port', 'maschine_out_port'],
            [maschine_in, melodics_in, melodics_out, maschine_out]
        ) if val is None]

        if missing:
            error_message = f"Missing MIDI ports: {', '.join(missing)}"
            log(error_message, f"Retrying in {retry_interval} seconds")
            time.sleep(retry_interval)
        else:
            error_message = None
            log("Detected ports:",
                      f"maschine_in_port = '{maschine_in}'",
                      f"melodics_in_port = '{melodics_in}'",
                      f"melodics_out_port = '{melodics_out}'",
                      f"maschine_out_port = '{maschine_out}'")
            return maschine_in, melodics_in, melodics_out, maschine_out

# ---------------------------------------------------------------------
# MIDI Forwarding
# ---------------------------------------------------------------------
def forward_to_app():
    CHANNEL_HIT = config.get("CHANNEL_HIT", 0)
    CHANNEL_PRESS = config.get("CHANNEL_PRESS", 1)
    CHANNEL_APP_SEND = config.get("CHANNEL_APP_SEND", 0)
    NOTE_MIN = config.get("NOTE_MIN", 48)
    NOTE_MAX = config.get("NOTE_MAX", 75)
    active_hits = set()

    while True:
        try:
            with mido.open_input(maschine_in_port) as inport, \
                 mido.open_output(melodics_in_port) as outport:

                while True:
                    for msg in inport.iter_pending():
                        if msg.type == "note_on" and msg.velocity == 0:
                            msg = mido.Message("note_off", note=msg.note, velocity=0, channel=msg.channel)
                        if not hasattr(msg, "channel"):
                            continue

                        # Default: send everything unless filtered
                        forwarded = False

                        # HIT
                        if msg.channel == CHANNEL_HIT:
                            if hasattr(msg, "note") and NOTE_MIN <= msg.note <= NOTE_MAX:
                                if msg.type == "note_on" and msg.note not in active_hits:
                                    msg.channel = CHANNEL_APP_SEND
                                    outport.send(msg)
                                    active_hits.add(msg.note)
                                    log_debug(f"[HIT] note_on {msg.note} vel={msg.velocity}")
                                    forwarded = True
                                elif msg.type == "note_off" and msg.note in active_hits:
                                    msg.channel = CHANNEL_APP_SEND
                                    outport.send(msg)
                                    active_hits.remove(msg.note)
                                    log_debug(f"[HIT] note_off {msg.note}")
                                    forwarded = True
                        # PRESS
                        elif msg.channel == CHANNEL_PRESS:
                            if hasattr(msg, "note") and NOTE_MIN <= msg.note <= NOTE_MAX and msg.note not in active_hits:
                                msg.channel = CHANNEL_APP_SEND
                                outport.send(msg)
                                log_debug(f"[PRESS] {msg.note} vel={msg.velocity}")
                                forwarded = True
                        # Other messages (catch-all for notes outside HIT/PRESS)
                        if not forwarded:
                           if msg.type in ["note_on", "note_off", "control_change", "sysex"]:
                               msg.channel = CHANNEL_APP_SEND
                               outport.send(msg)
                               log_debug(f"[FORWARDED OTHER] {msg}")

                    time.sleep(0.001)
        except Exception as e:
            global error_message
            error_message = str(e)
            log(f"Port error: {error_message}")
            time.sleep(5)

def forward_to_maschine():
    try:
        with mido.open_input(melodics_out_port) as inport, mido.open_output(maschine_out_port) as outport:
            while True:
                for msg in inport.iter_pending():
                    outport.send(msg)
                    log_debug(f"[Melodics -> Maschine] {msg}")
                time.sleep(0.001)
    except KeyboardInterrupt:
        return
    except Exception as e:
        global error_message
        error_message = str(e)
        log(f"Maschine forwarding error: {error_message}")

# ---------------------------------------------------------------------
# Start threads
# ---------------------------------------------------------------------
def start_listening(normal_mode=True):
    global threads
    if not threads:
        t_app = threading.Thread(target=forward_to_app, daemon=True)
        threads.append(t_app)
        t_app.start()
        if normal_mode:
            t_masch = threading.Thread(target=forward_to_maschine, daemon=True)
            threads.append(t_masch)
            t_masch.start()
        log(f"Listening started ({'Normal' if normal_mode else 'Dark'} mode)")

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
if __name__ == "__main__":
    mido.set_backend('mido.backends.rtmidi')
    config = load_config()

    # Ensure log file exists
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Log file created.\n")

    maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port = find_ports()
    setup_tray()
