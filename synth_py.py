#!/usr/bin/env python3
"""
OSINT Cinetic — Python synth (sostituzione Pure Data)

Riceve OSC su porta 9000, genera audio via sounddevice → PipeWire → WM8960.
Background: 24 oscillatori sinusoidali (220–588 Hz) sempre attivi.
Voci: triggerate dagli eventi OSC, con inviluppo attack/decay.
"""

import sys
import time
import threading
import numpy as np
import sounddevice as sd
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

SAMPLE_RATE = 48000
BLOCK_SIZE  = 1024
OSC_PORT    = 9000
MAX_VOICES  = 16

# Coro di background: 24 sinusoidi, 220–588 Hz (stesso schema di choir_voice.pd)
CHOIR_FREQS = np.array([220.0 + i * 16.0 for i in range(24)])
CHOIR_AMP   = 0.008   # per voce → somma ~0.19 RMS

# ─────────────────────────────────────────────
class Voice:
    """Voce polifonica triggerata da un evento OSC."""

    ATTACK_S = 0.010  # 10 ms attack

    def __init__(self, freq: float, amp: float, decay_ms: float):
        self.freq         = float(freq)
        self.amp          = float(amp) * 0.7
        self.decay_s      = max(float(decay_ms) / 1000.0, 0.05)
        self.phase        = 0.0
        self.phase_inc    = 2.0 * np.pi * self.freq / SAMPLE_RATE
        self.sample_pos   = 0
        self.attack_samp  = int(self.ATTACK_S * SAMPLE_RATE)
        self.active       = True

    def render(self, n: int) -> np.ndarray:
        t      = np.arange(n, dtype=np.float64)
        phases = self.phase + self.phase_inc * t
        self.phase = (phases[-1] + self.phase_inc) % (2.0 * np.pi)
        signal = np.sin(phases)

        pos = self.sample_pos + t
        # Attack lineare
        env = np.where(
            pos < self.attack_samp,
            pos / max(self.attack_samp, 1),
            np.exp(-4.0 * (pos - self.attack_samp) / (self.decay_s * SAMPLE_RATE))
        )

        self.sample_pos += n
        if env[-1] < 1e-4:
            self.active = False

        return signal * env * self.amp


# ─────────────────────────────────────────────
class Synth:
    def __init__(self):
        self.voices      = []
        self.lock        = threading.Lock()

        # Fasi oscillatori coro
        self.choir_phase     = np.zeros(len(CHOIR_FREQS))
        self.choir_phase_inc = 2.0 * np.pi * CHOIR_FREQS / SAMPLE_RATE

        # LFO lenti per modulazione ampiezza coro (0.05 Hz, fase random)
        self.lfo_phase     = np.random.uniform(0, 2.0 * np.pi, len(CHOIR_FREQS))
        self.lfo_phase_inc = 2.0 * np.pi * 0.05 / SAMPLE_RATE

    def trigger(self, freq: float, amp: float, reverb: float, decay_ms: float):
        with self.lock:
            self.voices = [v for v in self.voices if v.active]
            if len(self.voices) >= MAX_VOICES:
                self.voices.pop(0)
            self.voices.append(Voice(freq, amp, decay_ms))

    def _render_choir(self, n: int) -> np.ndarray:
        t      = np.arange(n, dtype=np.float64)
        out    = np.zeros(n)
        phases = self.choir_phase[:, None] + self.choir_phase_inc[:, None] * t
        self.choir_phase = (phases[:, -1] + self.choir_phase_inc) % (2.0 * np.pi)

        lfo_ph = self.lfo_phase[:, None] + self.lfo_phase_inc * t
        self.lfo_phase = (lfo_ph[:, -1] + self.lfo_phase_inc) % (2.0 * np.pi)
        amp_mod = 0.045 + 0.02 * np.sin(lfo_ph)  # [0.025 … 0.065]

        out = np.sum(np.sin(phases) * amp_mod, axis=0) * CHOIR_AMP
        return out

    def _render_voices(self, n: int) -> np.ndarray:
        out = np.zeros(n)
        with self.lock:
            for v in list(self.voices):
                if v.active:
                    out += v.render(n)
        return out

    def callback(self, outdata, frames, time_info, status):
        choir  = self._render_choir(frames)
        voices = self._render_voices(frames)
        mixed  = np.tanh(choir + voices).astype(np.float32)
        outdata[:, 0] = mixed
        outdata[:, 1] = mixed


# ─────────────────────────────────────────────
def find_output_device() -> int | None:
    """Cerca il device di output: prima 'pulse' (PipeWire PA), poi default."""
    devs = sd.query_devices()
    for i, d in enumerate(devs):
        if d['name'] == 'pulse' and d['max_output_channels'] >= 2:
            return i
    for i, d in enumerate(devs):
        if d['max_output_channels'] >= 2:
            return i
    return None


def run_osc_server(synth: Synth):
    def handler(address, *args):
        try:
            freq, amp, reverb, decay_ms = (float(a) for a in args[:4])
            synth.trigger(freq, amp, reverb, decay_ms)
        except Exception as e:
            print(f"[OSC] errore: {e}", file=sys.stderr)

    disp = Dispatcher()
    disp.map('/event', handler)
    server = BlockingOSCUDPServer(('127.0.0.1', OSC_PORT), disp)
    print(f"[OSC] in ascolto su porta {OSC_PORT}")
    server.serve_forever()


# ─────────────────────────────────────────────
if __name__ == '__main__':
    synth = Synth()

    dev = find_output_device()
    if dev is None:
        print("[AUDIO] Nessun device di output trovato.", file=sys.stderr)
        sys.exit(1)
    print(f"[AUDIO] Device: {sd.query_devices(dev)['name']} (index {dev})")

    osc_thread = threading.Thread(target=run_osc_server, args=(synth,), daemon=True)
    osc_thread.start()

    with sd.OutputStream(
        device=dev,
        samplerate=SAMPLE_RATE,
        channels=2,
        blocksize=BLOCK_SIZE,
        dtype='float32',
        callback=synth.callback,
    ):
        print("[AUDIO] Stream aperto. Ctrl+C per uscire.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStop.")
