import mido
import threading
import time
import re
import argparse
import json
from collections import defaultdict

mido.set_backend('mido.backends.rtmidi')

# Setup argument parser
parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true', help='Enable debug output')
args = parser.parse_args()

DEBUG = args.debug

def load_config(path='config.json'):
    with open(path, 'r') as f:
        return json.load(f)

# Debugging logger
def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

# ---------------------------------------------------------------------
#   Searches and sets required ports by config.json regexes
# ---------------------------------------------------------------------
def find_ports(retry_interval=5):
    """Continuously tries to find the MIDI ports defined in config.json."""

    patterns = config['patterns']

    while True:
        input_ports = mido.get_input_names()
        output_ports = mido.get_output_names()

        debug_print("🎹 Available input ports:")
        for p in input_ports:
            debug_print(f"  - {p}")

        debug_print("🎛 Available output ports:")
        for p in output_ports:
            debug_print(f"  - {p}")

        # Try to match ports
        maschine_in_port = next((p for p in input_ports if re.match(patterns['maschine_in_port'], p)), None)
        melodics_in_port = next((p for p in output_ports if re.match(patterns['melodics_in_port'], p)), None)
        melodics_out_port = next((p for p in input_ports if re.match(patterns['melodics_out_port'], p)), None)
        maschine_out_port = next((p for p in output_ports if re.match(patterns['maschine_out_port'], p)), None)

        missing = [name for name, val in zip(
            ['maschine_in_port', 'melodics_in_port', 'melodics_out_port', 'maschine_out_port'],
            [maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port]
        ) if val is None]

        if missing:
            print(f"⚠️  Missing MIDI ports: {', '.join(missing)}")
            print(f"🔁 Retrying in {retry_interval} seconds...\n")
            time.sleep(retry_interval)
        else:
            debug_print("✅ Detected ports:")
            debug_print(f"maschine_in_port = '{maschine_in_port}'")
            debug_print(f"melodics_in_port = '{melodics_in_port}'")
            debug_print(f"melodics_out_port = '{melodics_out_port}'")
            debug_print(f"maschine_out_port = '{maschine_out_port}'")

            return maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port

# ---------------------------------------------------------------------
#   MODIFIED FUNCTION — ONLY PRINT CHANNEL 2 (MIDO CHANNEL 1) MESSAGES
# ---------------------------------------------------------------------
def forward_to_app():
    """
    Forward Maschine HIT (channel 1) and PRESS (channel 2) events to Melodics.
    Handles multiple pads simultaneously, avoids double hits when HIT+PRESS occur.
    """

    CHANNEL_HIT = 0      # Maschine channel 1
    CHANNEL_PRESS = 1    # Maschine channel 2

    NOTE_MIN = config.get("NOTE_MIN", 48)
    NOTE_MAX = config.get("NOTE_MAX", 75)

    # Track currently active HIT notes to prevent duplicate sending
    active_hits = set()

    while True:
        try:
            with mido.open_input(maschine_in_port) as inport, \
                 mido.open_output(melodics_in_port) as outport:

                debug_print(f"🎧 Listening '{maschine_in_port}' → '{melodics_in_port}' (multi-pad safe)")

                while True:
                    for msg in inport.iter_pending():

                        # Convert note_on velocity=0 -> note_off
                        if msg.type == "note_on" and msg.velocity == 0:
                            msg = mido.Message("note_off", note=msg.note, velocity=0, channel=msg.channel)

                        if not hasattr(msg, "channel"):
                            debug_print(f"[IGNORED] {msg}")
                            continue

                        # ------------------------
                        # HIT channel
                        # ------------------------
                        if msg.channel == CHANNEL_HIT:
                            if hasattr(msg, "note") and NOTE_MIN <= msg.note <= NOTE_MAX:
                                if msg.type == "note_on":
                                    if msg.note not in active_hits:
                                        msg.channel = 0
                                        outport.send(msg)
                                        debug_print(f"🥁 [HIT] note_on {msg.note} vel={msg.velocity}")
                                        active_hits.add(msg.note)
                                elif msg.type == "note_off":
                                    if msg.note in active_hits:
                                        msg.channel = 0
                                        outport.send(msg)
                                        debug_print(f"🥁 [HIT] note_off {msg.note}")
                                        active_hits.remove(msg.note)
                            else:
                                # Forward any other HIT message
                                msg.channel = 0
                                outport.send(msg)
                                debug_print(f"🥁 [HIT MSG] {msg}")

                        # ------------------------
                        # PRESS channel
                        # ------------------------
                        elif msg.channel == CHANNEL_PRESS:
                            if hasattr(msg, "note") and NOTE_MIN <= msg.note <= NOTE_MAX:
                                if msg.note not in active_hits:
                                    msg.channel = 0
                                    outport.send(msg)
                                    debug_print(f"👉 [PRESS] {msg.note} vel={msg.velocity}")
                            else:
                                msg.channel = 0
                                outport.send(msg)
                                debug_print(f"👉 [PRESS] {msg.note} vel={getattr(msg, 'velocity', 'N/A')}")

                        # ------------------------
                        # Other messages
                        # ------------------------
                        elif msg.type == "control_change":
                            msg.channel = 0
                            outport.send(msg)
                            debug_print(f"[CC] {msg}")

                        elif msg.type == "sysex":
                            outport.send(msg)
                            debug_print(f"[SysEx] {msg}")

                    time.sleep(0.001)

        except Exception as e:
            debug_print(f"❌ Port error: {e}")
            debug_print("🔁 Retrying in 5 seconds...")
            time.sleep(5)

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

# ---------------------------------------------------------------------

if __name__ == "__main__":
    config = load_config()
    maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port = find_ports()

    # Start thread that prints channel-2 only
    app_thread = threading.Thread(target=forward_to_app, daemon=True)
    maschine_thread = threading.Thread(target=forward_to_maschine, daemon=True)

    app_thread.start()
    maschine_thread.start()

    debug_print("Running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting program.")
