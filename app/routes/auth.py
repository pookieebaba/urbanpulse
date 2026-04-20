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
