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
import time
import mido

def forward_to():
    """Forward Maschine HIT and PRESS events to Melodics, without debounce."""

    CHANNEL_HIT = 0     # Maschine Pad Hit (channel 1)
    CHANNEL_PRESS = 1   # Maschine Press (channel 2)

    # Prevent HIT and PRESS from same tap being forwarded twice
    LAST_EVENT_GAP = 0.020  # 20ms
    last_event_time = 0

    NOTE_MIN = config.get('NOTE_MIN', 48)
    NOTE_MAX = config.get('NOTE_MAX', 75)

    while True:
        try:
            with mido.open_input(maschine_in_port) as inport, \
                 mido.open_output(melodics_in_port) as outport:

                debug_print(f"🎧 Listening '{maschine_in_port}' → '{melodics_in_port}' (no debounce)...\n")

                while True:
                    for msg in inport.iter_pending():

                        now = time.time()

                        # Convert note_on velocity=0 -> note_off
                        if msg.type == "note_on" and msg.velocity == 0:
                            msg = mido.Message("note_off", note=msg.note, velocity=0,
                                               channel=msg.channel)

                        # ------------------------------------------------------------------
                        #   GLOBAL GAP: avoid PRESS+HIT firing instantly together
                        # ------------------------------------------------------------------
                        if now - last_event_time < LAST_EVENT_GAP:
                            continue

                        # ===============================================================
                        #   HIT (channel 0)
                        # ===============================================================
                        if hasattr(msg, "channel") and msg.channel == CHANNEL_HIT:

                            if msg.type == "note_on" and msg.velocity > 0:
                                if NOTE_MIN <= msg.note <= NOTE_MAX:
                                    msg.channel = 0
                                    debug_print(f"🥁 [HIT→Melodics] {msg}")
                                    outport.send(msg)
                                    last_event_time = now
                                continue

                            elif msg.type == "note_off":
                                if NOTE_MIN <= msg.note <= NOTE_MAX:
                                    msg.channel = 0
                                    debug_print(f"🥁 [RELEASE→Melodics] {msg}")
                                    outport.send(msg)
                                    last_event_time = now
                                continue

                            else:
                                msg.channel = 0
                                debug_print(f"🥁 [HIT MSG→Melodics] {msg}")
                                outport.send(msg)
                                last_event_time = now
                                continue

                        # ===============================================================
                        #   PRESS (channel 1)
                        # ===============================================================
                        elif hasattr(msg, "channel") and msg.channel == CHANNEL_PRESS:

                            msg.channel = 0
                            debug_print(f"👉 [PRESS→Melodics] {msg}")
                            outport.send(msg)
                            last_event_time = now
                            continue

                        # ===============================================================
                        #   OTHER MESSAGES
                        # ===============================================================
                        elif msg.type == "control_change":
                            msg.channel = 0
                            debug_print(f"[CC→Melodics] {msg}")
                            outport.send(msg)
                            last_event_time = now
                            continue

                        elif msg.type == "sysex":
                            debug_print(f"[SysEx→Melodics] {msg}")
                            outport.send(msg)
                            last_event_time = now
                            continue

                        else:
                            debug_print(f"[IGNORED] {msg}")

                    time.sleep(0.001)

        except Exception as e:
            debug_print(f"❌ Port error: {e}")
            debug_print("🔁 Retrying in 5 seconds...\n")
            time.sleep(5)

# ---------------------------------------------------------------------

if __name__ == "__main__":
    config = load_config()
    maschine_in_port, melodics_in_port, melodics_out_port, maschine_out_port = find_ports()

    # Start both MIDI forwarding threads
    t1 = threading.Thread(target=forward_to, daemon=True)
    t2 = threading.Thread(target=forward_to, daemon=True)
    
    t1.start()
    t2.start()

    debug_print("Running MIDI forwarders. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        debug_print("\nExiting program.")
