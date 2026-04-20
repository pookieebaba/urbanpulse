#!/usr/bin/env python3
"""
UrbanPulse — IoT Sensor Simulator
Emits realistic sensor readings for all city zones every INTERVAL seconds.
Reads zone list from the API, then continuously POSTs readings to /api/sensors/bulk-ingest.

Usage:
    python scripts/sensor_simulator.py [--interval 30] [--base-url http://localhost:5000]
"""
import argparse
import math
import random
import time
import logging
from datetime import datetime

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SIMULATOR] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SENSOR_KEY = "simulator-key-change-in-prod"

# Base AQI profiles per zone index (repeats via modulo)
BASE_AQI_PROFILES = [
    {"name": "industrial",   "base": 120, "variance": 40},
    {"name": "residential",  "base": 65,  "variance": 20},
    {"name": "commercial",   "base": 85,  "variance": 30},
    {"name": "park",         "base": 40,  "variance": 15},
    {"name": "transport_hub","base": 140, "variance": 50},
]


def diurnal_factor(hour: int) -> float:
    """Traffic-linked AQI peaks at 8 AM and 6 PM."""
    morning_peak = math.exp(-0.5 * ((hour - 8) / 2) ** 2)
    evening_peak = math.exp(-0.5 * ((hour - 18) / 2) ** 2)
    return 1.0 + 0.4 * max(morning_peak, evening_peak)


def generate_reading(zone_id: str, zone_index: int) -> dict:
    profile = BASE_AQI_PROFILES[zone_index % len(BASE_AQI_PROFILES)]
    hour = datetime.utcnow().hour

    base_aqi = profile["base"] * diurnal_factor(hour)
    aqi = max(5.0, base_aqi + random.gauss(0, profile["variance"]))

    # Occasionally inject a spike (1% chance)
    if random.random() < 0.01:
        aqi *= random.uniform(1.5, 2.5)
        log.warning("SPIKE injected for zone %s: AQI=%.1f", zone_id, aqi)

    pm25 = aqi * random.uniform(0.30, 0.50)
    pm10 = pm25 * random.uniform(1.5, 2.5)
    co2_ppm = 400 + aqi * random.uniform(0.8, 1.4)
    nox_ppb = aqi * random.uniform(0.10, 0.25)
    noise_db = 45 + profile["base"] * 0.15 + random.gauss(0, 5)
    temp_c = 22 + 8 * math.sin(2 * math.pi * (hour - 6) / 24) + random.gauss(0, 1)
    humidity = 55 - 15 * math.sin(2 * math.pi * hour / 24) + random.gauss(0, 3)
    wind_speed = max(0, random.gauss(3.5, 1.5))

    return {
        "zone_id": zone_id,
        "aqi": round(aqi, 2),
        "pm25": round(pm25, 2),
        "pm10": round(pm10, 2),
        "co2_ppm": round(co2_ppm, 1),
        "nox_ppb": round(nox_ppb, 2),
        "noise_db": round(noise_db, 1),
        "temp_c": round(temp_c, 1),
        "humidity_pct": round(max(10, min(100, humidity)), 1),
        "wind_speed_ms": round(wind_speed, 2),
    }


def fetch_zones(base_url: str) -> list:
    try:
        resp = requests.get(f"{base_url}/api/zones", timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as exc:
        log.error("Could not fetch zones: %s", exc)
        return []


def run(base_url: str, interval: int):
    log.info("Starting simulator → %s (interval=%ds)", base_url, interval)

    zones = []
    while not zones:
        zones = fetch_zones(base_url)
        if not zones:
            log.warning("No zones found, retrying in 10s…")
            time.sleep(10)

    log.info("Loaded %d zones", len(zones))

    session = requests.Session()
    session.headers.update({"X-Sensor-Key": SENSOR_KEY})

    iteration = 0
    while True:
        iteration += 1
        batch = [
            generate_reading(z["zone_id"], i)
            for i, z in enumerate(zones)
        ]

        try:
            resp = session.post(
                f"{base_url}/api/sensors/bulk-ingest",
                json=batch,
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            log.info(
                "Iter %d — ingested %d readings (errors: %d)",
                iteration,
                result.get("data", {}).get("inserted", 0),
                len(result.get("data", {}).get("errors", [])),
            )
        except Exception as exc:
            log.error("Ingest error: %s", exc)

        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UrbanPulse sensor simulator")
    parser.add_argument("--interval", type=int, default=30, help="Emit interval in seconds")
    parser.add_argument("--base-url", default="http://localhost:5000", help="API base URL")
    args = parser.parse_args()
    run(args.base_url, args.interval)
