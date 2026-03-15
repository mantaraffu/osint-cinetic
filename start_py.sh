#!/bin/bash
# OSINT Cinetic — avvio con synth Python (sounddevice → PipeWire)
# Richiede: pip install sounddevice python-osc numpy

cd "$(dirname "$0")"

pkill -f "synth_py.py" 2>/dev/null
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

python3 synth_py.py >> logs/synth.log 2>&1 &
echo "Python synth avviato (PID $!)"
sleep 2

python fetcher_stream.py >> logs/fetcher_out.log 2>&1 &
echo "Fetcher avviato (PID $!)"
