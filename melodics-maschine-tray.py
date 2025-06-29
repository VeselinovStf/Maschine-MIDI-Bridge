import mido
import threading
import time
import re
import argparse
import subprocess
import sys

#  Saves tiny disk I/O time when running from source.
sys.dont_write_bytecode = True

from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw
import signal
import json
from collections import defaultdict
import mido.backends.rtmidi

# Ports
# maschine_in_port = 'Maschine MK3 Ctrl MIDI 2'   # Physical Maschine input (pad hits)
# melodics_in_port = 'loopMIDI IN 4'              # Melodics input (receives from script)
# melodics_out_port = 'loopMIDI OUT 4'            # Melodics output (feedback to script)
# maschine_out_port = 'Maschine MK3 Ctrl MIDI 3'  # Maschine output (pad lights)

# Setup argument parser
parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true', help='Enable debug output')
args = parser.parse_args()

# Set DEBUG based on command line arg
DEBUG = args.debug
error_message = None

def create_image():
    """Create an icon image (simple circle)."""
    img = Image.new('RGB', (64, 64), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 48, 48), fill='white')
    return img

def setup_tray():
    """Create and run the system tray icon."""
    def on_quit(icon, item):
        icon.stop()
        sys.exit()

    def on_show_error(icon, item):
        from tkinter import messagebox, Tk
        root = Tk()
        root.withdraw()  # Hide main window
        messagebox.showerror("MIDI Port Error", error_message or "No error.")
        root.destroy()

    def on_restart(icon, item):
        icon.stop()
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit()

    menu_items = []

    if error_message:
        menu_items += [
            MenuItem("⚠ Show Port Error", on_show_error),
            MenuItem("🔄 Retry", on_restart)
        ]

    menu_items.append(MenuItem('Exit', on_quit))

    menu = Menu(*menu_items)
    icon = Icon("MelodicsMaschineV1_1", create_image(), menu=menu)
    icon.run()

# Load external configuration
# Load config.json
# {
#     "NOTE_MIN": 48,
#     "NOTE_MAX": 75,
#     "patterns": {
#         "maschine_in_port": "^Maschine MK3 Ctrl MIDI \\d+$",
#         "melodics_in_port": "^loopMIDI IN \\d+$",
#         "melodics_out_port": "^loopMIDI OUT \\d+$",
#         "maschine_out_port": "^Maschine MK3 Ctrl MIDI \\d+$"
#     }
# }
# maschine_in_port = 'Maschine MK3 Ctrl MIDI 2'   # Physical Maschine input (pad hits)
# melodics_in_port = 'loopMIDI IN 4'              # Melodics input (receives from script)
# melodics_out_port = 'loopMIDI OUT 4'            # Melodics output (feedback to script)
# maschine_out_port = 'Maschine MK3 Ctrl MIDI 3'  # Maschine output (pad lights)
def load_config(path='config.json'):
    with open(path, 'r') as f:
        return json.load(f)

# Installing dependencies from requirement.txt file
def install_requirements():
    try:
        import mido, rtmidi  # Attempt to import
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        sys.exit()

# Searches and sets required ports by config.json regexes
def find_ports():
    global error_message

    patterns = config['patterns']
    input_ports = mido.get_input_names()
    output_ports = mido.get_output_names()

    def find_matching(pattern, port_list):
        for port in port_list:
            if re.match(pattern, port):
                return port
        return None

    maschine_in_port = find_matching(patterns['maschine_in_port'], input_ports)
    melodics_in_port = find_matching(patterns['melodics_in_port'], output_ports)
    melodics_out_port = find_matching(patterns['melodics_out_port'], input_ports)
    maschine_out_port = find_matching(patterns['maschine_out_port'], output_ports)

    missing_ports = [name for name, val in zip(
        ['maschine_in_port', 'melodics_in_port', 'melodics_out_port', 'maschine_out_port'],
        [maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port]
    ) if val is None]

    if missing_ports:
        error_message = f"Missing MIDI ports: {', '.join(missing_ports)}"
        return None

    return maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port

# Forwards from maschine to melodics 
def forward_to_melodics():
    # Track last event time per note
    recent_notes = defaultdict(lambda: 0)
    DEBOUNCE_MS = config.get('DEBOUNCE_MS', 0.04)

    NOTE_MIN = config.get('NOTE_MIN', 48)
    NOTE_MAX = config.get('NOTE_MAX', 75)

    """Listen to Maschine input, filter and send to Melodics."""
    try:
        with mido.open_input(maschine_in_port) as inport, mido.open_output(melodics_in_port) as outport:
            while True:
                for msg in inport.iter_pending():
                    now = time.time()

                    # Convert note_on with velocity 0 to note_off
                    if msg.type == 'note_on' and msg.velocity == 0:
                        msg = mido.Message('note_off', note=msg.note, velocity=0, channel=msg.channel)

                    if msg.type == 'note_off' and NOTE_MIN <= msg.note <= NOTE_MAX:
                        msg.channel = 0
                        outport.send(msg)
                    # Only one of press/hit should trigger a send
                    elif msg.type in ['note_on', 'note_off'] and NOTE_MIN <= msg.note <= NOTE_MAX:
                        # Check last sent time for this note
                        last_time = recent_notes[msg.note]
                        if now - last_time > DEBOUNCE_MS:
                            recent_notes[msg.note] = now
                            msg.channel = 0  # Adjust channel for Melodics
                            outport.send(msg)
                        else:
                            continue
                    elif msg.type == 'control_change':
                        msg.channel = 0
                        outport.send(msg)
                    elif msg.type == 'sysex':
                        outport.send(msg)
                    else:
                        continue
                time.sleep(0.001)
    except KeyboardInterrupt:
        return

# Forwards from melodics to maschine
def forward_to_maschine():
    """Listen to Melodics output and forward to Maschine output for pad lights."""
    try:
        with mido.open_input(melodics_out_port) as inport, mido.open_output(maschine_out_port) as outport:
            while True:
                for msg in inport.iter_pending():
                    outport.send(msg)
                time.sleep(0.001)
    except KeyboardInterrupt:
        return

if __name__ == "__main__":
    install_requirements()
    mido.set_backend('mido.backends.rtmidi')
    config = load_config()

    ports = find_ports()

    if ports:
        maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port = ports

        # Start both MIDI forwarding threads
        t1 = threading.Thread(target=forward_to_melodics, daemon=True)
        t2 = threading.Thread(target=forward_to_maschine, daemon=True)
        t1.start()
        t2.start()

    # Always run tray (whether ports succeeded or failed)
    setup_tray()