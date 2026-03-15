#!/bin/bash
# OSINT Cinetic — avvio con Pure Data (pipeline legacy)
# Richiede: pipewire-jack, pd, mrpeach (udpreceive/unpackOSC/routeOSC)

cd "$(dirname "$0")"

pkill -f "pd -nogui" 2>/dev/null
pkill -f "fetcher_stream.py" 2>/dev/null
sleep 1

# Inizializza mixer WM8960
amixer -c wm8960soundcard sset 'Speaker' 127,127 > /dev/null 2>&1
amixer -c wm8960soundcard sset 'Headphone' 109,109 > /dev/null 2>&1
amixer -c wm8960soundcard sset 'Playback' 255,255 > /dev/null 2>&1
amixer -c wm8960soundcard cset name='Left Output Mixer PCM Playback Switch' on > /dev/null 2>&1
amixer -c wm8960soundcard cset name='Right Output Mixer PCM Playback Switch' on > /dev/null 2>&1

for i in $(seq 1 10); do
  wpctl status > /dev/null 2>&1 && break
  sleep 1
done

# Pure Data via PipeWire JACK — OSC su porta 9000
# Nota: il fetcher invia 5 parametri ma Pd usa solo i primi 4 (event_code ignorato)
pw-jack pd -nogui -jack -noadc \
  -lib mrpeach/udpreceive \
  -lib mrpeach/unpackOSC \
  -lib mrpeach/routeOSC \
  synth/osint.pd >> logs/pd.log 2>&1 &

echo "Pd avviato (PID $!)"
sleep 3

python fetcher_stream.py >> logs/fetcher_out.log 2>&1 &
echo "Fetcher avviato (PID $!)"
