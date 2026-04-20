import uuid
from datetime import datetime
from app import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
import enum


# ─────────────────────────────────────────────
#  Enums
# ─────────────────────────────────────────────

class RiskLevel(enum.IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class AlertSeverity(str, enum.Enum):
    WATCH = "watch"
    WARNING = "warning"
    EMERGENCY = "emergency"


class ReportCategory(str, enum.Enum):
    DRAIN = "drain"
    DUMPING = "dumping"
    AIR = "air"
    NOISE = "noise"
    WATER = "water"
    OTHER = "other"


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class BadgeType(str, enum.Enum):
    FIRST_REPORT = "first_report"
    TEN_REPORTS = "ten_reports"
    FIFTY_REPORTS = "fifty_reports"
    VERIFIED_REPORTER = "verified_reporter"
    ZONE_GUARDIAN = "zone_guardian"


# ─────────────────────────────────────────────
#  Zone
# ─────────────────────────────────────────────

class Zone(db.Model):
    __tablename__ = "zones"

    zone_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)  # e.g. "Z-04-N"
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    area_km2 = db.Column(db.Float)
    population = db.Column(db.Integer)
    risk_level = db.Column(db.Integer, default=RiskLevel.LOW)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sensor_readings = db.relationship("SensorReading", backref="zone", lazy="dynamic", cascade="all, delete-orphan")
    alerts = db.relationship("Alert", backref="zone", lazy="dynamic", cascade="all, delete-orphan")
    reports = db.relationship("IssueReport", backref="zone", lazy="dynamic", cascade="all, delete-orphan")
    citizens = db.relationship("Citizen", backref="home_zone", lazy="dynamic", foreign_keys="Citizen.home_zone_id")

    def current_aqi(self):
        latest = (
            self.sensor_readings
            .order_by(SensorReading.recorded_at.desc())
            .first()
        )
        return round(latest.aqi, 1) if latest else None

    def to_dict(self, include_aqi=True):
        d = {
            "zone_id": str(self.zone_id),
            "name": self.name,
            "code": self.code,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "area_km2": self.area_km2,
            "population": self.population,
            "risk_level": self.risk_level,
            "description": self.description,
        }
        if include_aqi:
            d["current_aqi"] = self.current_aqi()
        return d


# ─────────────────────────────────────────────
#  Sensor Reading
# ─────────────────────────────────────────────

class SensorReading(db.Model):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        db.Index("idx_sensor_zone_time", "zone_id", "recorded_at"),
    )

    reading_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    zone_id = db.Column(UUID(as_uuid=True), db.ForeignKey("zones.zone_id"), nullable=False)

    aqi = db.Column(db.Float, nullable=False)          # 0–500 (EPA standard)
    pm25 = db.Column(db.Float)                         # μg/m³
    pm10 = db.Column(db.Float)                         # μg/m³
    co2_ppm = db.Column(db.Float)                      # parts per million
    nox_ppb = db.Column(db.Float)                      # parts per billion
    noise_db = db.Column(db.Float)                     # decibels
    temp_c = db.Column(db.Float)                       # Celsius
    humidity_pct = db.Column(db.Float)                 # 0–100
    wind_speed_ms = db.Column(db.Float)                # m/s
    is_anomaly = db.Column(db.Boolean, default=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "reading_id": self.reading_id,
            "zone_id": str(self.zone_id),
            "aqi": round(self.aqi, 2),
            "pm25": self.pm25,
            "pm10": self.pm10,
            "co2_ppm": self.co2_ppm,
            "nox_ppb": self.nox_ppb,
            "noise_db": self.noise_db,
            "temp_c": self.temp_c,
            "humidity_pct": self.humidity_pct,
            "wind_speed_ms": self.wind_speed_ms,
            "is_anomaly": self.is_anomaly,
            "recorded_at": self.recorded_at.isoformat() + "Z",
        }

    @staticmethod
    def aqi_category(aqi_value):
        if aqi_value is None:
            return "unknown"
        if aqi_value <= 50:
            return "good"
        elif aqi_value <= 100:
            return "moderate"
        elif aqi_value <= 150:
            return "unhealthy_sensitive"
        elif aqi_value <= 200:
            return "unhealthy"
        elif aqi_value <= 300:
            return "very_unhealthy"
        return "hazardous"


# ─────────────────────────────────────────────
#  Citizen
# ─────────────────────────────────────────────

class Citizen(db.Model):
    __tablename__ = "citizens"

    citizen_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(200), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    home_zone_id = db.Column(UUID(as_uuid=True), db.ForeignKey("zones.zone_id"))
    points = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    alert_prefs = db.Column(JSONB, default=lambda: {
        "email_alerts": True,
        "in_app_alerts": True,
        "min_severity": "watch"
    })
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    reports = db.relationship("IssueReport", backref="reporter", lazy="dynamic", foreign_keys="IssueReport.citizen_id")
    badges = db.relationship("CitizenBadge", backref="citizen", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "citizen_id": str(self.citizen_id),
            "name": self.name,
            "email": self.email,
            "home_zone_id": str(self.home_zone_id) if self.home_zone_id else None,
            "points": self.points,
            "is_admin": self.is_admin,
            "alert_prefs": self.alert_prefs,
            "created_at": self.created_at.isoformat() + "Z",
        }


class CitizenBadge(db.Model):
    __tablename__ = "citizen_badges"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    citizen_id = db.Column(UUID(as_uuid=True), db.ForeignKey("citizens.citizen_id"), nullable=False)
    badge_type = db.Column(SAEnum(BadgeType), nullable=False)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "badge_type": self.badge_type.value,
            "awarded_at": self.awarded_at.isoformat() + "Z",
        }


# ─────────────────────────────────────────────
#  Alert
# ─────────────────────────────────────────────

class Alert(db.Model):
    __tablename__ = "alerts"
    __table_args__ = (
        db.Index("idx_alert_zone_active", "zone_id", "is_active"),
    )

    alert_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_id = db.Column(UUID(as_uuid=True), db.ForeignKey("zones.zone_id"), nullable=False)
    severity = db.Column(SAEnum(AlertSeverity), nullable=False)
    aqi_value = db.Column(db.Float, nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "alert_id": str(self.alert_id),
            "zone_id": str(self.zone_id),
            "zone_name": self.zone.name if self.zone else None,
            "severity": self.severity.value,
            "aqi_value": self.aqi_value,
            "message": self.message,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() + "Z",
            "resolved_at": self.resolved_at.isoformat() + "Z" if self.resolved_at else None,
        }


# ─────────────────────────────────────────────
#  Issue Report
# ─────────────────────────────────────────────

class IssueReport(db.Model):
    __tablename__ = "issue_reports"

    report_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    citizen_id = db.Column(UUID(as_uuid=True), db.ForeignKey("citizens.citizen_id"), nullable=False)
    zone_id = db.Column(UUID(as_uuid=True), db.ForeignKey("zones.zone_id"), nullable=False)
    category = db.Column(SAEnum(ReportCategory), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    status = db.Column(SAEnum(ReportStatus), default=ReportStatus.PENDING)
    upvotes = db.Column(db.Integer, default=0)
    image_url = db.Column(db.String(500))
    admin_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_reporter=False):
        d = {
            "report_id": str(self.report_id),
            "zone_id": str(self.zone_id),
            "zone_name": self.zone.name if self.zone else None,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "status": self.status.value,
            "upvotes": self.upvotes,
            "image_url": self.image_url,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }
        if include_reporter:
            d["reporter_name"] = self.reporter.name if self.reporter else None
        return d
