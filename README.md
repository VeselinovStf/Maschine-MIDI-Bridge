# 🎹 Melodics ⇄ Maschine MIDI Bridge

## Motivation

Native Instruments Maschine — like many modern MIDI controllers — is designed to work seamlessly with its own software. However, when used with third-party applications like Melodics, pad sensitivity and responsiveness may degrade, especially when trying to play lightly or expressively.

This bridge solves that problem by forwarding MIDI smartly between **Maschine MK3** and **Melodics**, preserving:

- ✅ Accurate response with soft playing — no need to strike pads hard  
- ✅ Visual feedback from Melodics to Maschine  
- ✅ Expressive performance for finger drumming and rhythm training  

It allows Maschine to behave as it does in its native environment, while fully functional with Melodics.

---

## Script Features

- Forward pad hits from Maschine to Melodics  
- Return visual pad feedback (lights) from Melodics to Maschine  
- Configurable note ranges, ports

## Tray Features

- Forward pad hits from Maschine to Melodics  
- Normal Mode - Return visual pad feedback (lights) from Melodics to Maschine  
- Dark Mode - Stop pad colouring from Melodics    
- Configurable note ranges, ports, debaunce value

## Config File

- In the config_files folder is placed the Melodics config + additional key mappings

---

## Disclaimer

- This project is **not affiliated** with or endorsed by Melodics.

---

## Releases

- [MelodicsMaschine EXE](https://github.com/VeselinovStf/Maschine-MIDI-Bridge/releases/)  

---

## NI Control Editor Settings

- Pads: C3 → D#4 (all pads)  
- HIT channel: 1  
- PRESS channel: 2, threshold as desired  

**Recommended settings:**  
- Pad velocity curve: Soft3  
- PRESS threshold: 2  
- Pads sensitivity: maximum  

![Hit Setting](images/mk3Hit.png)  
![Press Setting](images/mk3Press.png)  
![General Settings](images/mk3Pref.png)  

## Melodics Settings

- Place Config file in: C:\Users\{USER}\AppData\Local\Melodics\Melodics\devices
- Inside Melodics Settings this: select the Virtual MIDI Bus Device

---

## 📦 Requirements

### Build Tools (Windows)

If building from source, install **Microsoft C++ Build Tools**:

1. Download [Build Tools for Visual Studio 2022](https://visualstudio.microsoft.com/visual-cpp-build-tools/)  
2. During installation, select:
   - ✔ Desktop development with C++  
   - ✔ Under **Individual components**, add:
     - MSVC v143 toolset  
     - Windows 10/11 SDK  
     - CMake (optional)

### Python Libraries

- Python 3.7+  
- `mido` – MIDI library  
- `python-rtmidi` – backend for MIDI  
- `pystray` & `Pillow` – tray app support  

Install via:

```bash
pip install -r requirements.txt
```

or individually:

```bash
pip install mido python-rtmidi pystray pillow
```

### Virtual MIDI

- [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) – create IN and OUT ports  

---

## Config (`config.json`)

The script requires a config file for port names, note ranges, and debounce timing:

```json
{
    "DEBOUNCE_MS": 0.0170,
    "CHANNEL_APP_SEND": 0,
    "DEBUG": false,
    "NOTE_MIN": 48,
    "NOTE_MAX": 75,
    "patterns": {
        "maschine_in_port": "^Maschine MK3 Ctrl MIDI \\d+$",
        "melodics_in_port": "^loopMIDI IN \\d+$",
        "melodics_out_port": "^loopMIDI OUT \\d+$",
        "maschine_out_port": "^Maschine MK3 Ctrl MIDI \\d+$"
    }
}
```
- NOTE: The config channels are 0 based, those in Controll Editor are 1 based

- You can modify `NOTE_MIN`, `NOTE_MAX`, and patterns to match different controllers or MIDI setups.

---

## Run the Script (CLI Version)

```bash
python midi-bridge.py
```

- Enable debug output:

```bash
python midi-bridge.py --debug
```

- Stop with **Ctrl+C**.

---

## Background Tray App (Windows `.exe`)

Convert the tray script to a background app:

```bash
pyinstaller --noconsole --onefile .\midi-bridge-win-tray.py --name=MelodicsMaschine_v2_01
```

- The `.exe` will:
  - Run in the background
  - Show a tray icon
  - Allow stopping and viewing logs
  - Auto-detect missing ports  

**Notes:**

- Place `config.json` in the same folder as the `.exe`.  
- You may need admin rights to build/run.

---

## 🧠 How It Works

- **Maschine → Melodics**: forwards pad hits (C3–D#4) to loopMIDI IN.  
- **Melodics → Maschine**: forwards feedback to Maschine to light up pads in Normal Mode.  
- Handles NoteOn/NoteOff and control change messages.  
- Only forwards valid notes on configured channels.
- Any additional Melodics commands may be send wia the config file
---

## 🎛️ Port Auto-Detection

Ports are matched using regular expressions:

| Logical Name       | Pattern                     | Direction |
|-------------------|-----------------------------|-----------|
| maschine_in_port   | Maschine MK3 Ctrl MIDI \\d+ | MIDI IN   |
| melodics_in_port   | loopMIDI IN \\d+             | MIDI OUT  |
| melodics_out_port  | loopMIDI OUT \\d+            | MIDI IN   |
| maschine_out_port  | Maschine MK3 Ctrl MIDI \\d+ | MIDI OUT  |

- Port numbers changing is not a problem; matching uses names.

---

## 🔧 LoopMIDI Setup

1. Create **loopMIDI IN** and **loopMIDI OUT** ports  
2. Configure Melodics:
   - Input: loopMIDI IN  
   - Output: loopMIDI OUT  

![loopMIDI Setup](images/loopMidiSetUp.png)

---

## 🛠️ Troubleshooting

- **OSError: unknown port** → Make sure ports exist and are visible.  
- Switching devices in Melodics may mute loopMIDI channels → restart the app.  
- Turning off Maschine while Melodics is open may disable pad lights.

---

## 📝 Customization

- Modify `config.json` for note ranges, ports, and debounce.  
- Adjust velocity curves and thresholds in Maschine preferences.

---

## 💡 Startup (Windows)

- Create a shortcut to your `.exe` , place the exe and the config in:

```
C:\Users\<USER_NAME>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
```

---

## © License

MIT – Use freely, credit appreciated.