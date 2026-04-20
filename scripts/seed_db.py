#!/usr/bin/env python3
"""
Seed the database with city zones, an admin user, and 60 days of
historical sensor data for ML forecasting.

Usage (from project root):
    flask --app run.py seed-db
OR:
    python scripts/seed_db.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import random
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

CITY_ZONES = [
    {"name": "Sector 1 Industrial",   "code": "Z01-IND", "lat": 30.9010, "lng": 75.8573, "pop": 12000},
    {"name": "Sector 2 Residential",  "code": "Z02-RES", "lat": 30.9050, "lng": 75.8620, "pop": 45000},
    {"name": "Sector 3 Commercial",   "code": "Z03-COM", "lat": 30.9090, "lng": 75.8660, "pop": 28000},
    {"name": "Sector 4 Park Zone",    "code": "Z04-PRK", "lat": 30.9130, "lng": 75.8700, "pop": 5000},
    {"name": "Sector 5 Transport Hub","code": "Z05-TRN", "lat": 30.9170, "lng": 75.8740, "pop": 18000},
    {"name": "Sector 6 Residential",  "code": "Z06-RES", "lat": 30.9210, "lng": 75.8780, "pop": 52000},
    {"name": "Sector 7 Commercial",   "code": "Z07-COM", "lat": 30.9250, "lng": 75.8820, "pop": 31000},
    {"name": "Sector 8 Industrial",   "code": "Z08-IND", "lat": 30.9290, "lng": 75.8860, "pop": 9000},
    {"name": "Sector 9 University",   "code": "Z09-EDU", "lat": 30.9330, "lng": 75.8900, "pop": 22000},
    {"name": "Sector 10 Market",      "code": "Z10-MKT", "lat": 30.9370, "lng": 75.8940, "pop": 38000},
    {"name": "Sector 11 Residential", "code": "Z11-RES", "lat": 30.9410, "lng": 75.8980, "pop": 41000},
    {"name": "Sector 12 Hospital",    "code": "Z12-MED", "lat": 30.9450, "lng": 75.9020, "pop": 14000},
    {"name": "Sector 13 Suburb",      "code": "Z13-SUB", "lat": 30.9490, "lng": 75.9060, "pop": 27000},
    {"name": "Sector 14 Green Belt",  "code": "Z14-GRN", "lat": 30.9530, "lng": 75.9100, "pop": 3000},
    {"name": "Sector 15 Commercial",  "code": "Z15-COM", "lat": 30.9570, "lng": 75.9140, "pop": 36000},
    {"name": "Sector 16 Residential", "code": "Z16-RES", "lat": 30.9610, "lng": 75.9180, "pop": 48000},
    {"name": "Sector 17 Industrial",  "code": "Z17-IND", "lat": 30.9650, "lng": 75.9220, "pop": 11000},
    {"name": "Sector 18 Transport",   "code": "Z18-TRN", "lat": 30.9690, "lng": 75.9260, "pop": 16000},
    {"name": "Sector 19 Suburb",      "code": "Z19-SUB", "lat": 30.9730, "lng": 75.9300, "pop": 25000},
    {"name": "Sector 20 City Centre", "code": "Z20-CTR", "lat": 30.9770, "lng": 75.9340, "pop": 60000},
]

BASE_AQI = {
    "IND": 130, "COM": 90, "RES": 60, "TRN": 145, "PRK": 38,
    "EDU": 55, "MKT": 105, "MED": 50, "SUB": 55, "GRN": 30, "CTR": 100,
}


def zone_base_aqi(code: str) -> int:
    suffix = code.split("-")[-1]
    return BASE_AQI.get(suffix, 75)


def historical_aqi(base: int, dt: datetime) -> float:
    hour = dt.hour
    day_of_week = dt.weekday()  # 0=Monday

    diurnal = 1.0 + 0.35 * (
        math.exp(-0.5 * ((hour - 8) / 2) ** 2)
        + math.exp(-0.5 * ((hour - 18) / 2) ** 2)
    )
    weekend_factor = 0.85 if day_of_week >= 5 else 1.0
    seasonal = 1.0 + 0.10 * math.sin(2 * math.pi * dt.timetuple().tm_yday / 365)

    aqi = base * diurnal * weekend_factor * seasonal + random.gauss(0, base * 0.10)
    return max(5.0, aqi)


def run_seed():
    from app import create_app, db
    from app.models import Zone, Citizen, SensorReading

    app = create_app("development")
    with app.app_context():
        print("Dropping and recreating tables…")
        db.drop_all()
        db.create_all()

        # ── Zones ──────────────────────────────────────────────────────────
        print(f"Seeding {len(CITY_ZONES)} zones…")
        zone_objects = []
        for z in CITY_ZONES:
            zone = Zone(
                name=z["name"],
                code=z["code"],
                latitude=z["lat"],
                longitude=z["lng"],
                population=z["pop"],
                area_km2=round(random.uniform(2, 15), 2),
            )
            db.session.add(zone)
            zone_objects.append(zone)
        db.session.flush()

        # ── Admin user ─────────────────────────────────────────────────────
        admin = Citizen(
            name="City Admin",
            email="admin@urbanpulse.city",
            password_hash=generate_password_hash("Admin@1234"),
            is_admin=True,
        )
        db.session.add(admin)

        # ── Demo citizen ───────────────────────────────────────────────────
        demo = Citizen(
            name="Demo Citizen",
            email="citizen@urbanpulse.city",
            password_hash=generate_password_hash("Demo@1234"),
            home_zone_id=zone_objects[1].zone_id,
        )
        db.session.add(demo)

        # ── Historical sensor readings (60 days, hourly) ───────────────────
        print("Seeding 60 days of historical sensor data… (this may take ~30s)")
        now = datetime.utcnow()
        batch_size = 500
        batch = []
        total = 0

        for zone in zone_objects:
            base = zone_base_aqi(zone.code)
            dt = now - timedelta(days=60)
            while dt <= now:
                aqi = historical_aqi(base, dt)
                pm25 = aqi * random.uniform(0.30, 0.50)
                reading = SensorReading(
                    zone_id=zone.zone_id,
                    aqi=round(aqi, 2),
                    pm25=round(pm25, 2),
                    pm10=round(pm25 * random.uniform(1.5, 2.5), 2),
                    co2_ppm=round(400 + aqi * random.uniform(0.8, 1.4), 1),
                    nox_ppb=round(aqi * random.uniform(0.10, 0.25), 2),
                    noise_db=round(45 + base * 0.15 + random.gauss(0, 5), 1),
                    temp_c=round(22 + 8 * math.sin(2 * math.pi * (dt.hour - 6) / 24), 1),
                    humidity_pct=round(random.uniform(40, 80), 1),
                    wind_speed_ms=round(max(0, random.gauss(3.5, 1.5)), 2),
                    recorded_at=dt,
                )
                batch.append(reading)
                total += 1
                if len(batch) >= batch_size:
                    db.session.bulk_save_objects(batch)
                    db.session.flush()
                    batch = []
                    print(f"  {total:,} readings inserted…", end="\r")
                dt += timedelta(hours=1)

        if batch:
            db.session.bulk_save_objects(batch)

        db.session.commit()
        print(f"\n✅ Seeded {total:,} sensor readings across {len(zone_objects)} zones.")
        print("Admin login  → admin@urbanpulse.city / Admin@1234")
        print("Citizen login → citizen@urbanpulse.city / Demo@1234")


if __name__ == "__main__":
    run_seed()
