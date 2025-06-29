import mido
import threading
import time
import mido
import re
import argparse
import subprocess
import sys
import json

mido.set_backend('mido.backends.rtmidi')

# Ports
# maschine_in_port = 'Maschine MK3 Ctrl MIDI 2'   # Physical Maschine input (pad hits)
# melodics_in_port = 'loopMIDI IN 4'              # Melodics input (receives from script)
# melodics_out_port = 'loopMIDI OUT 4'            # Melodics output (feedback to script)
# maschine_out_port = 'Maschine MK3 Ctrl MIDI 3'  # Maschine output (pad lights)

# Load external configuration
def load_config(path='config.json'):
    with open(path, 'r') as f:
        return json.load(f)

# Setup argument parser
parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true', help='Enable debug output')
args = parser.parse_args()

# Set DEBUG based on command line arg
DEBUG = args.debug

def install_requirements():
    try:
        import mido, rtmidi  # Attempt to import
    except ImportError:
        print("🔧 Installing missing dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Done. Please restart the script.")
        sys.exit()

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

def find_ports():
    # Patterns to match (case sensitive)
    patterns = config['patterns']

    input_ports = mido.get_input_names()
    output_ports = mido.get_output_names()

    # Find Maschine input port (physical Maschine Ctrl MIDI input)
    maschine_in_port = None
    for port in input_ports:
        if re.match(patterns['maschine_in_port'], port):
            maschine_in_port = port
            break

    # Find Melodics input port (loopMIDI IN) — this is where script sends data to Melodics
    melodics_in_port = None
    for port in output_ports:
        if re.match(patterns['melodics_in_port'], port):
            melodics_in_port = port
            break

    # Find Melodics output port (loopMIDI OUT) — feedback from Melodics to script
    melodics_out_port = None
    for port in input_ports:
        if re.match(patterns['melodics_out_port'], port):
            melodics_out_port = port
            break

    # Find Maschine output port (physical Maschine Ctrl MIDI output)
    maschine_out_port = None
    for port in output_ports:
        if re.match(patterns['maschine_out_port'], port):
            maschine_out_port = port
            break

    if None in [maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port]:
        missing = [name for name, val in zip(
            ['maschine_in_port', 'melodics_in_port', 'melodics_out_port', 'maschine_out_port'],
            [maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port]
        ) if val is None]
        raise RuntimeError(f"Could not find the following MIDI ports: {', '.join(missing)}")

    debug_print("Detected ports:")
    debug_print(f"maschine_in_port = '{maschine_in_port}'")
    debug_print(f"melodics_in_port = '{melodics_in_port}'")
    debug_print(f"melodics_out_port = '{melodics_out_port}'")
    debug_print(f"maschine_out_port = '{maschine_out_port}'")

    return maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port


def forward_to_melodics():
    NOTE_MIN = config.get('NOTE_MIN', 48)
    NOTE_MAX = config.get('NOTE_MAX', 75)

    """Listen to Maschine input, filter and send to Melodics."""
    try:
        with mido.open_input(maschine_in_port) as inport, mido.open_output(melodics_in_port) as outport:
            debug_print(f"Listening on Maschine input '{maschine_in_port}', forwarding to Melodics '{melodics_in_port}'...")
            while True:
                for msg in inport.iter_pending():
                    # Convert note_on with velocity 0 to note_off
                    if msg.type == 'note_on' and msg.velocity == 0:
                        msg = mido.Message('note_off', note=msg.note, velocity=0, channel=msg.channel)
                    
                    # Filter by channel and note range
                    if msg.type in ['note_on', 'note_off'] and msg.channel == 1 and NOTE_MIN <= msg.note <= NOTE_MAX:
                        msg.channel = 0  # Adjust channel for Melodics if needed
                        debug_print(f"[Maschine→Melodics] Forwarding {msg}")
                        outport.send(msg)
                    elif msg.type == 'control_change':
                        msg.channel = 0
                        debug_print(f"[Maschine→Melodics] Forwarding CC {msg}")
                        outport.send(msg)
                    else:
                        debug_print(f"[Maschine→Melodics] Ignored {msg}")
                time.sleep(0.001)
    except KeyboardInterrupt:
        debug_print("\n[Maschine→Melodics] Stopped.")

import time
from collections import defaultdict



def forward_to_melodics():
    # Track last event time per note
    recent_notes = defaultdict(lambda: 0)
    DEBOUNCE_MS = 0.04  # 40 milliseconds

    NOTE_MIN = config.get('NOTE_MIN', 48)
    NOTE_MAX = config.get('NOTE_MAX', 75)

    """Listen to Maschine input, filter and send to Melodics."""
    try:
        with mido.open_input(maschine_in_port) as inport, mido.open_output(melodics_in_port) as outport:
            debug_print(f"Listening on Maschine input '{maschine_in_port}', forwarding to Melodics '{melodics_in_port}'...")

            while True:
                for msg in inport.iter_pending():
                    now = time.time()

                    # Convert note_on with velocity 0 to note_off
                    if msg.type == 'note_on' and msg.velocity == 0:
                        msg = mido.Message('note_off', note=msg.note, velocity=0, channel=msg.channel)

                    if msg.type == 'note_off' and NOTE_MIN <= msg.note <= NOTE_MAX:
                        msg.channel = 0
                        debug_print(f"[Maschine→Melodics] Forwarding NOTE_OFF {msg}")
                        outport.send(msg)
                    # Only one of press/hit should trigger a send
                    elif msg.type in ['note_on', 'note_off'] and NOTE_MIN <= msg.note <= NOTE_MAX:
                        # Check last sent time for this note
                        last_time = recent_notes[msg.note]
                        if now - last_time > DEBOUNCE_MS:
                            recent_notes[msg.note] = now
                            msg.channel = 0  # Adjust channel for Melodics
                            debug_print(f"[Maschine→Melodics] Forwarding {msg}")
                            outport.send(msg)
                        else:
                            debug_print(f"[Maschine→Melodics] Skipped duplicate {msg}")
                    elif msg.type == 'control_change':
                        msg.channel = 0
                        debug_print(f"[Maschine→Melodics] Forwarding CC {msg}")
                        outport.send(msg)
                    elif msg.type == 'sysex':
                        debug_print(f"[Maschine→Melodics] Forwarding SysEx {msg}")
                        outport.send(msg)
                    else:
                        debug_print(f"[Maschine→Melodics] Ignored {msg}")
                time.sleep(0.001)
    except KeyboardInterrupt:
        debug_print("\n[Maschine→Melodics] Stopped.")


def forward_to_maschine():
    """Listen to Melodics output and forward to Maschine output for pad lights."""
    try:
        with mido.open_input(melodics_out_port) as inport, mido.open_output(maschine_out_port) as outport:
            debug_print(f"Listening on '{melodics_out_port}', forwarding to '{maschine_out_port}'...")
            while True:
                for msg in inport.iter_pending():
                    debug_print(f"Forwarding: {msg}")
                    outport.send(msg)
                time.sleep(0.001)
    except KeyboardInterrupt:
        debug_print("\nExiting on user request.")

if __name__ == "__main__":
    install_requirements()
    config = load_config()
    maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port = find_ports()

    # Start both MIDI forwarding threads
    t1 = threading.Thread(target=forward_to_melodics, daemon=True)
    t2 = threading.Thread(target=forward_to_maschine, daemon=True)
    
    t1.start()
    t2.start()

    debug_print("Running MIDI forwarders. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        debug_print("\nExiting program.")
