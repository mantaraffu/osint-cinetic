import json
import math
import time
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from pythonosc import udp_client

from connectors.gdelt import GdeltConnector

CAGLIARI        = (39.2238, 9.1217)
OSC_HOST        = "127.0.0.1"
OSC_PORT        = 9000
STATE_FILE      = Path("state.json")
LOG_FILE        = Path("logs/fetcher.log")
POLL_INTERVAL   = 15 * 60
MIN_INTERVAL    = 1.0    # secondi minimi tra un evento e l'altro
MAX_INTERVAL    = 120.0  # secondi massimi (evita silenzi troppo lunghi)
MAX_SEEN_IDS    = 5000

FREQ_MAP = {
    "190": 330.0,
    "191": 110.0,
    "192": 165.0,
    "193": 880.0,
    "194": 220.0,
    "195": 440.0,
    "196": 660.0,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)


def haversine(lat1, lng1, lat2, lng2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def distance_to_audio(distance_km, event_code):
    MAX_DIST = 15000.0
    d      = min(distance_km, MAX_DIST) / MAX_DIST
    amp    = round(max(0.02, 1.0 - (d ** 0.7) * 0.97), 3)
    reverb = round(min(0.92, d ** 0.8 * 0.93), 3)
    decay  = int(800 + d * 9200)
    freq   = FREQ_MAP.get(event_code, 330.0)
    return {"freq": freq, "amp": amp, "reverb": reverb,
            "decay_ms": decay, "distance_km": round(distance_km, 1)}


def load_state():
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()).get("seen_ids", []))
        except Exception:
            pass
    return set()


def save_state(seen_ids):
    STATE_FILE.write_text(json.dumps({"seen_ids": list(seen_ids)[-MAX_SEEN_IDS:]}))


def main():
    connector = GdeltConnector()
    osc       = udp_client.SimpleUDPClient(OSC_HOST, OSC_PORT)
    seen_ids  = load_state()

    log.info("=" * 60)
    log.info("OSINT CINETIC — avvio streaming")
    log.info(f"Punto fisso: Cagliari {CAGLIARI}")
    log.info(f"OSC target: {OSC_HOST}:{OSC_PORT}")
    log.info(f"ID già processati: {len(seen_ids)}")
    log.info("=" * 60)

    while True:
        log.info("── Fetch GDELT ──────────────────────────────────")
        events = connector.fetch_all()

        new_events = []
        for event in events:
            event_id = event.raw.get("id", event.source_url) if event.raw else event.source_url
            if event_id not in seen_ids:
                new_events.append((event_id, event))

        n = len(new_events)
        if n > 0:
            interval = min(max(POLL_INTERVAL / n, MIN_INTERVAL), MAX_INTERVAL)
        else:
            interval = 0
        log.info(f"{n} nuovi eventi da inviare"
                 + (f" — intervallo {interval:.1f}s (totale ~{n*interval/60:.1f} min)" if n else ""))

        for event_id, event in new_events:
            seen_ids.add(event_id)
            event_code = event.raw.get("event_code", "190") if event.raw else "190"
            distance   = haversine(CAGLIARI[0], CAGLIARI[1], event.lat, event.lng)
            audio      = distance_to_audio(distance, event_code)

            log.info(
                f"  ► {event.event_type:20s} | {event.location_name[:30]:30s} | "
                f"{audio['distance_km']:7.0f} km | "
                f"freq={audio['freq']:5.0f} Hz  amp={audio['amp']:.2f}  "
                f"rev={audio['reverb']:.2f}  decay={audio['decay_ms']}ms"
            )

            try:
                osc.send_message("/event", [
                    float(audio["freq"]),
                    float(audio["amp"]),
                    float(audio["reverb"]),
                    float(audio["decay_ms"]),
                    int(event_code),
                ])
            except Exception as e:
                log.warning(f"  OSC send fallito: {e}")

            output = {**asdict(event), **audio, "event_id": event_id}
            output.pop("raw", None)
            print(json.dumps(output, ensure_ascii=False))

            time.sleep(interval)

        save_state(seen_ids)

        # Se gli eventi hanno già occupato i 15 min, fetch subito; altrimenti aspetta il resto
        elapsed = n * interval
        remaining = max(0, POLL_INTERVAL - elapsed)
        if remaining > 0:
            log.info(f"Stato salvato. Prossimo fetch tra {remaining/60:.1f} min.")
            time.sleep(remaining)
        else:
            log.info("Stato salvato. Fetch immediato (eventi hanno coperto l'intervallo).")


if __name__ == "__main__":
    main()
