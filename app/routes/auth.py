from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from app import db, limiter
from app.models import Citizen, Zone
from app.utils.validators import validate_email, validate_password
from app.utils.response import success, error

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("10 per hour")
def register():
    data = request.get_json()
    if not data:
        return error("Request body required", 400)

    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    home_zone_id = data.get("home_zone_id")

    # Validate inputs
    if not name or len(name) < 2:
        return error("Name must be at least 2 characters", 400)
    if not validate_email(email):
        return error("Invalid email address", 400)
    if not validate_password(password):
        return error(
            "Password must be at least 8 characters with at least one number", 400
        )

    if Citizen.query.filter_by(email=email).first():
        return error("Email already registered", 409)

    # Validate zone if provided
    if home_zone_id:
        zone = Zone.query.get(home_zone_id)
        if not zone:
            return error("Invalid home zone", 400)

    citizen = Citizen(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        home_zone_id=home_zone_id,
    )
    db.session.add(citizen)
    db.session.commit()

    access_token = create_access_token(identity=str(citizen.citizen_id))
    refresh_token = create_refresh_token(identity=str(citizen.citizen_id))

    return success(
        {
            "citizen": citizen.to_dict(),
            "access_token": access_token,
            "refresh_token": refresh_token,
        },
        "Registration successful",
        201,
    )


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("20 per hour")
def login():
    data = request.get_json()
    if not data:
        return error("Request body required", 400)

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    citizen = Citizen.query.filter_by(email=email, is_active=True).first()

    if not citizen or not check_password_hash(citizen.password_hash, password):
        return error("Invalid email or password", 401)

    citizen.last_login = datetime.utcnow()
    db.session.commit()

    access_token = create_access_token(identity=str(citizen.citizen_id))
    refresh_token = create_refresh_token(identity=str(citizen.citizen_id))

    return success(
        {
            "citizen": citizen.to_dict(),
            "access_token": access_token,
            "refresh_token": refresh_token,
        },
        "Login successful",
    )


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    citizen_id = get_jwt_identity()
    access_token = create_access_token(identity=citizen_id)
    return success({"access_token": access_token})


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    citizen_id = get_jwt_identity()
    citizen = Citizen.query.get(citizen_id)
    if not citizen:
        return error("User not found", 404)

    profile = citizen.to_dict()
    profile["badges"] = [b.to_dict() for b in citizen.badges]
    profile["report_count"] = citizen.reports.count()

    return success(profile)


@auth_bp.route("/me", methods=["PATCH"])
@jwt_required()
def update_profile():
    citizen_id = get_jwt_identity()
    citizen = Citizen.query.get(citizen_id)
    if not citizen:
        return error("User not found", 404)

    data = request.get_json() or {}

    if "name" in data and len(data["name"].strip()) >= 2:
        citizen.name = data["name"].strip()

    if "home_zone_id" in data:
        zone = Zone.query.get(data["home_zone_id"])
        if not zone:
            return error("Invalid zone", 400)
        citizen.home_zone_id = data["home_zone_id"]

    if "alert_prefs" in data and isinstance(data["alert_prefs"], dict):
        prefs = citizen.alert_prefs or {}
        prefs.update(data["alert_prefs"])
        citizen.alert_prefs = prefs

    db.session.commit()
    return success(citizen.to_dict(), "Profile updated")


@auth_bp.route("/me/password", methods=["PUT"])
@jwt_required()
def change_password():
    citizen_id = get_jwt_identity()
    citizen = Citizen.query.get(citizen_id)

    data = request.get_json() or {}
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not check_password_hash(citizen.password_hash, old_password):
        return error("Current password is incorrect", 400)

    if not validate_password(new_password):
        return error("New password does not meet requirements", 400)

    citizen.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return success(message="Password updated successfully")

@auth_bp.route("/setup", methods=["GET"])
def setup():
    """One-time database setup — delete this route after running!"""
    try:
        from app import db
        from app.models import Zone, Citizen, SensorReading
        import math, random
        from datetime import datetime, timedelta
        from werkzeug.security import generate_password_hash

        db.create_all()

        # Only seed if empty
        if Zone.query.count() > 0:
            return {"status": "already seeded", "zones": Zone.query.count()}

        # Seed zones
        zones_data = [
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

        BASE_AQI = {"IND": 130, "COM": 90, "RES": 60, "TRN": 145,
                    "PRK": 38, "EDU": 55, "MKT": 105, "MED": 50,
                    "SUB": 55, "GRN": 30, "CTR": 100}

        zone_objects = []
        for z in zones_data:
            zone = Zone(name=z["name"], code=z["code"],
                       latitude=z["lat"], longitude=z["lng"],
                       population=z["pop"], area_km2=round(random.uniform(2,15),2))
            db.session.add(zone)
            zone_objects.append((zone, z["code"]))
        db.session.flush()

        # Admin user
        admin = Citizen(
            name="City Admin", email="admin@urbanpulse.city",
            password_hash=generate_password_hash("Admin@1234"),
            is_admin=True,
        )
        db.session.add(admin)

        # Demo citizen
        demo = Citizen(
            name="Demo Citizen", email="citizen@urbanpulse.city",
            password_hash=generate_password_hash("Demo@1234"),
            home_zone_id=zone_objects[1][0].zone_id,
        )
        db.session.add(demo)

        # Seed 7 days of hourly readings (lighter than 60 days)
        now = datetime.utcnow()
        batch = []
        for zone, code in zone_objects:
            suffix = code.split("-")[-1]
            base = BASE_AQI.get(suffix, 75)
            dt = now - timedelta(days=7)
            while dt <= now:
                hour = dt.hour
                diurnal = 1.0 + 0.35 * (
                    math.exp(-0.5*((hour-8)/2)**2) +
                    math.exp(-0.5*((hour-18)/2)**2)
                )
                aqi = max(5.0, base * diurnal + random.gauss(0, base*0.10))
                pm25 = aqi * random.uniform(0.30, 0.50)
                reading = SensorReading(
                    zone_id=zone.zone_id,
                    aqi=round(aqi, 2),
                    pm25=round(pm25, 2),
                    pm10=round(pm25 * random.uniform(1.5, 2.5), 2),
                    co2_ppm=round(400 + aqi * random.uniform(0.8, 1.4), 1),
                    noise_db=round(45 + base * 0.15 + random.gauss(0, 5), 1),
                    temp_c=round(22 + 8 * math.sin(2*math.pi*(dt.hour-6)/24), 1),
                    humidity_pct=round(random.uniform(40, 80), 1),
                    wind_speed_ms=round(max(0, random.gauss(3.5, 1.5)), 2),
                    recorded_at=dt,
                )
                batch.append(reading)
                dt += timedelta(hours=1)

        db.session.bulk_save_objects(batch)
        db.session.commit()

        return {
            "status": "success",
            "zones": Zone.query.count(),
            "citizens": Citizen.query.count(),
            "readings": SensorReading.query.count(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500