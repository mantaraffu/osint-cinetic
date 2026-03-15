# OSINT Cinetic

Installazione sonora generativa che trasforma eventi militari globali in suono in tempo reale.

I dati vengono scaricati da **GDELT 2.0** ogni 15 minuti, filtrati per tipologia militare (codici CAMEO 190–196) e inviati via **OSC** a un motore **SuperCollider** che li sonifica in base alla distanza geografica da Cagliari.

---

## Architettura

```
GDELT 2.0 (ogni 15 min)
    └── fetcher_stream.py
         └── OSC /event → SuperCollider (scsynth)
                            ├── \bell      background etéreo continuo
                            ├── \combat    scontri armati (190–193, 196)
                            └── \bomb      bombardamenti / attacchi aerei (194–195)
                                └── PipeWire → WM8960 HAT → speaker / jack
```

---

## Struttura

```
osint-cinetic/
├── start.sh                # Script di avvio
├── fetcher_stream.py       # Loop fetch → filtra → OSC
├── state.json              # ID eventi già processati (non versionato)
├── connectors/
│   ├── base.py             # Classe astratta OsintConnector + NormalizedEvent
│   └── gdelt.py            # Connettore GDELT 2.0
├── synth/
│   ├── osint_sc.scd        # Patch SuperCollider (SynthDef + OSC receiver)
│   ├── osint.pd            # Patch Pure Data (legacy)
│   ├── voice.pd            # Voce singola Pd (legacy)
│   └── choir_voice.pd      # Coro Pd (legacy)
└── logs/                   # Log runtime (non versionato)
```

---

## Requisiti

**Sistema:**
- Raspberry Pi con HAT **WM8960** (speaker + jack 3.5mm)
- Raspberry Pi OS Bookworm 64-bit
- `pipewire`, `pipewire-jack`, `wireplumber`

**Pacchetti:**
```bash
sudo apt install supercollider-server sc3-plugins
```

**Python:**
```bash
pip install python-osc requests
```

**`/boot/firmware/config.txt`** (necessario per JACK su I2S):
```
dtparam=i2s=on
dtoverlay=i2s-mmap
dtoverlay=wm8960-soundcard
```

---

## Avvio

Sono disponibili tre pipeline audio, tutte con lo stesso fetcher GDELT.

### SuperCollider (consigliata)
```bash
bash start.sh
```
Avvia `sclang` → `scsynth` via `pw-jack`. Richiede `supercollider-server`, `sc3-plugins`.

### Python / sounddevice
```bash
bash start_py.sh
```
Sintesi in Python puro via `sounddevice → PipeWire`. Richiede `pip install sounddevice numpy python-osc`.

### Pure Data (legacy)
```bash
bash start_pd.sh
```
Avvia `pd -nogui` via `pw-jack`. Richiede `pd` e libreria `mrpeach`. Il 5° parametro OSC (`event_code`) viene ignorato dalla patch Pd.

---

Tutti gli script inizializzano i mixer ALSA del WM8960 e attendono che PipeWire sia pronto prima di avviare il motore audio.

---

## Mappatura sonora

Il punto di riferimento geografico è **Cagliari** (39.2238°N, 9.1217°E).

### Background — `\bell`
24 campane FM in loop continuo (55–330 Hz), decay 5–11s, riverbero ampio.
Sempre attivo, indipendente dagli eventi.

### Voci eventi

| Codice CAMEO | Tipo                      | SynthDef   | Frequenza   |
|--------------|---------------------------|------------|-------------|
| 190          | Forza militare            | `\combat`  | 330 Hz      |
| 191          | Blocco                    | `\combat`  | 110 Hz      |
| 192          | Occupazione               | `\combat`  | 165 Hz      |
| 193          | Armi leggere              | `\combat`  | 880 → 500 Hz (capped) |
| 194          | Artiglieria / Blindati    | `\bomb`    | grave (~55 Hz) |
| 195          | Attacco aereo             | `\bomb`    | grave (~110 Hz) |
| 196          | Violazione cessate fuoco  | `\combat`  | 660 → 500 Hz (capped) |

### Parametri in funzione della distanza

| Parametro     | Logica                                              |
|---------------|-----------------------------------------------------|
| Ampiezza      | Inversamente proporzionale alla distanza (max 1.0, min 0.02) |
| Reverb mix    | Proporzionale alla distanza (max 0.92)              |
| Decay         | Da 800 ms (vicino) a 10.000 ms (lontano, max 15.000 km) |

---

## OSC

Il fetcher invia messaggi OSC a `127.0.0.1:9000`:

```
/event  [freq: float, amp: float, reverb: float, decay_ms: float, event_code: int]
```

SuperCollider ascolta su porta 9000 via `thisProcess.openUDPPort(9000)`.

---

## Filtraggio eventi GDELT

- `EventRootCode == 19` (uso della forza)
- `EventCode` in `{190–196}`
- `ActionGeo_Type >= 3` (localizzazione città o più precisa)
- Esclusi eventi con URL contenente: `police`, `gang`, `murder`, `crime`, `drug`, `theft`, `arrest`

Per ogni ciclo vengono processati al massimo i **50 eventi** con punteggio più alto,
distribuiti uniformemente nei **15 minuti** successivi al fetch.
