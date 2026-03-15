#!/bin/bash
# OSINT Cinetic — startup script
# Requires: pipewire-jack installed, wm8960soundcard HAT

cd "$(dirname "$0")"

# Kill any existing instances
pkill -f "pd -nogui" 2>/dev/null
pkill -f "fetcher_stream.py" 2>/dev/null
sleep 1

# Inizializza mixer WM8960 (i valori vengono persi ad ogni riavvio)
amixer -c wm8960soundcard sset 'Speaker' 127,127 > /dev/null 2>&1
amixer -c wm8960soundcard sset 'Headphone' 109,109 > /dev/null 2>&1
amixer -c wm8960soundcard sset 'Playback' 255,255 > /dev/null 2>&1
amixer -c wm8960soundcard cset name='Left Output Mixer PCM Playback Switch' on > /dev/null 2>&1
amixer -c wm8960soundcard cset name='Right Output Mixer PCM Playback Switch' on > /dev/null 2>&1

# Aspetta che PipeWire sia pronto
for i in $(seq 1 10); do
  wpctl status > /dev/null 2>&1 && break
  sleep 1
done

# Start SuperCollider (sclang avvia scsynth internamente via pw-jack)
QT_QPA_PLATFORM=offscreen pw-jack sclang synth/osint_sc.scd >> logs/sc.log 2>&1 &
echo "SuperCollider avviato (PID $!)"
sleep 10  # attende che scsynth sia pronto e i SynthDef caricati

# Start GDELT fetcher
python fetcher_stream.py >> logs/fetcher_out.log 2>&1 &
echo "Fetcher avviato (PID $!)"
