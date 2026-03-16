# OSINT Cinetic

A generative sound installation that transforms global military events into real-time sound.

Data is fetched from **GDELT 2.0** every 15 minutes, filtered by military event type (CAMEO codes 190–196), and sent via **OSC** to a **SuperCollider** engine that sonifies events based on geographic distance from Cagliari.

---

## Architecture

```
GDELT 2.0 (every 15 min)
    └── fetcher_stream.py
         └── OSC /event → SuperCollider (scsynth)
                            ├── \bell      continuous ethereal background
                            ├── \combat    armed conflicts (190–193, 196)
                            └── \bomb      bombardments / airstrikes (194–195)
                                └── PipeWire → WM8960 HAT → speaker / jack
```

---

## Structure

```
osint-cinetic/
├── start.sh                # Startup script
├── fetcher_stream.py       # Fetch loop → filter → OSC
├── state.json              # Already-processed event IDs (not versioned)
├── connectors/
│   ├── base.py             # Abstract OsintConnector class + NormalizedEvent
│   └── gdelt.py            # GDELT 2.0 connector
├── synth/
│   ├── osint_sc.scd        # SuperCollider patch (SynthDef + OSC receiver)
│   ├── osint.pd            # Pure Data patch (legacy)
│   ├── voice.pd            # Single Pd voice (legacy)
│   └── choir_voice.pd      # Pd choir (legacy)
└── logs/                   # Runtime logs (not versioned)
```

---

## Requirements

**System:**
- Raspberry Pi with **WM8960** HAT (speaker + 3.5mm jack)
- Raspberry Pi OS Bookworm 64-bit
- `pipewire`, `pipewire-jack`, `wireplumber`

**Packages:**
```bash
sudo apt install supercollider-server sc3-plugins
```

**Python:**
```bash
pip install python-osc requests
```

**`/boot/firmware/config.txt`** (required for JACK over I2S):
```
dtparam=i2s=on
dtoverlay=i2s-mmap
dtoverlay=wm8960-soundcard
```

---

## Running

Three audio pipelines are available, all sharing the same GDELT fetcher.

### SuperCollider (recommended)
```bash
bash start.sh
```
Launches `sclang` → `scsynth` via `pw-jack`. Requires `supercollider-server`, `sc3-plugins`.

### Python / sounddevice
```bash
bash start_py.sh
```
Pure Python synthesis via `sounddevice → PipeWire`. Requires `pip install sounddevice numpy python-osc`.

### Pure Data (legacy)
```bash
bash start_pd.sh
```
Launches `pd -nogui` via `pw-jack`. Requires `pd` and the `mrpeach` library. The 5th OSC parameter (`event_code`) is ignored by the Pd patch.

---

All scripts initialize the WM8960 ALSA mixers and wait for PipeWire to be ready before starting the audio engine.

---

## Sound Mapping

The geographic reference point is **Cagliari** (39.2238°N, 9.1217°E).

### Background — `\bell`
24 FM bells in continuous loop (55–330 Hz), decay 5–11s, wide reverb.
Always active, independent of incoming events.

### Event voices

| CAMEO Code | Type                       | SynthDef   | Frequency              |
|------------|----------------------------|------------|------------------------|
| 190        | Military force             | `\combat`  | 330 Hz                 |
| 191        | Blockade                   | `\combat`  | 110 Hz                 |
| 192        | Occupation                 | `\combat`  | 165 Hz                 |
| 193        | Small arms                 | `\combat`  | 880 → 500 Hz (capped)  |
| 194        | Artillery / Armored attack | `\bomb`    | low (~55 Hz)           |
| 195        | Airstrike                  | `\bomb`    | low (~110 Hz)          |
| 196        | Ceasefire violation        | `\combat`  | 660 → 500 Hz (capped)  |

### Distance-based parameters

| Parameter  | Logic                                                          |
|------------|----------------------------------------------------------------|
| Amplitude  | Inversely proportional to distance (max 1.0, min 0.02)        |
| Reverb mix | Proportional to distance (max 0.92)                           |
| Decay      | From 800 ms (nearby) to 10,000 ms (distant, max 15,000 km)   |

---

## OSC

The fetcher sends OSC messages to `127.0.0.1:9000`:

```
/event  [freq: float, amp: float, reverb: float, decay_ms: float, event_code: int]
```

SuperCollider listens on port 9000 via `thisProcess.openUDPPort(9000)`.

---

## GDELT Event Filtering

- `EventRootCode == 19` (use of force)
- `EventCode` in `{190–196}`
- `ActionGeo_Type >= 3` (city-level or more precise geolocation)
- Events excluded if URL contains: `police`, `gang`, `murder`, `crime`, `drug`, `theft`, `arrest`

Per fetch cycle, at most **50 events** with the highest score are processed,
distributed evenly over the **15 minutes** following the fetch.
