"""
UrbanPulse — Test Suite
Run with:  pytest tests/ -v --cov=app --cov-report=term-missing
"""
import pytest
from app import create_app, db as _db
from app.models import Zone, Citizen, SensorReading
from werkzeug.security import generate_password_hash
import uuid


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def db(app):
    return _db


@pytest.fixture(scope="session")
def test_zone(db):
    zone = Zone(
        name="Test Zone Alpha",
        code="TZ-ALPHA",
        latitude=30.90,
        longitude=75.85,
        population=10000,
    )
    db.session.add(zone)
    db.session.commit()
    return zone


@pytest.fixture(scope="session")
def test_citizen(db, test_zone):
    citizen = Citizen(
        name="Test User",
        email="test@urbanpulse.city",
        password_hash=generate_password_hash("Test@1234"),
        home_zone_id=test_zone.zone_id,
    )
    db.session.add(citizen)
    db.session.commit()
    return citizen


@pytest.fixture(scope="session")
def admin_citizen(db):
    admin = Citizen(
        name="Admin User",
        email="admin_test@urbanpulse.city",
        password_hash=generate_password_hash("Admin@1234"),
        is_admin=True,
    )
    db.session.add(admin)
    db.session.commit()
    return admin


@pytest.fixture
def citizen_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "test@urbanpulse.city", "password": "Test@1234"},
    )
    return resp.get_json()["data"]["access_token"]


@pytest.fixture
def admin_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin_test@urbanpulse.city", "password": "Admin@1234"},
    )
    return resp.get_json()["data"]["access_token"]


# ─── Health Check ─────────────────────────────────────────────────────────────

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


# ─── Auth ─────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_register_success(self, client, test_zone):
        resp = client.post("/api/auth/register", json={
            "name": "New User",
            "email": f"new_{uuid.uuid4().hex[:6]}@test.com",
            "password": "Passw0rd!",
            "home_zone_id": str(test_zone.zone_id),
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert "access_token" in data["data"]

    def test_register_duplicate_email(self, client):
        resp = client.post("/api/auth/register", json={
            "name": "Dup User",
            "email": "test@urbanpulse.city",
            "password": "Passw0rd!",
        })
        assert resp.status_code == 409

    def test_register_invalid_email(self, client):
        resp = client.post("/api/auth/register", json={
            "name": "Bad Email",
            "email": "not-an-email",
            "password": "Passw0rd!",
        })
        assert resp.status_code == 400

    def test_register_weak_password(self, client):
        resp = client.post("/api/auth/register", json={
            "name": "Weak Pass",
            "email": "weak@test.com",
            "password": "abc",
        })
        assert resp.status_code == 400

    def test_login_success(self, client):
        resp = client.post("/api/auth/login", json={
            "email": "test@urbanpulse.city",
            "password": "Test@1234",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.get_json()["data"]

    def test_login_wrong_password(self, client):
        resp = client.post("/api/auth/login", json={
            "email": "test@urbanpulse.city",
            "password": "WrongPass1",
        })
        assert resp.status_code == 401

    def test_me_requires_auth(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_token(self, client, citizen_token):
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {citizen_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["email"] == "test@urbanpulse.city"


# ─── Zones ────────────────────────────────────────────────────────────────────

class TestZones:
    def test_list_zones(self, client, test_zone):
        resp = client.get("/api/zones")
        assert resp.status_code == 200
        zones = resp.get_json()["data"]
        assert isinstance(zones, list)
        assert len(zones) >= 1

    def test_get_zone(self, client, test_zone):
        resp = client.get(f"/api/zones/{test_zone.zone_id}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["code"] == "TZ-ALPHA"

    def test_get_zone_not_found(self, client):
        resp = client.get(f"/api/zones/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_zone_summary(self, client, test_zone):
        resp = client.get(f"/api/zones/{test_zone.zone_id}/summary")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "avg_aqi" in data

    def test_create_zone_admin_only(self, client, citizen_token):
        resp = client.post(
            "/api/zones",
            json={"name": "New Zone", "code": "Z-NEW", "latitude": 30.9, "longitude": 75.9},
            headers={"Authorization": f"Bearer {citizen_token}"},
        )
        assert resp.status_code == 403

    def test_create_zone_as_admin(self, client, admin_token):
        resp = client.post(
            "/api/zones",
            json={"name": "Admin Zone", "code": "Z-ADM", "latitude": 30.95, "longitude": 75.95},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201


# ─── Sensors ──────────────────────────────────────────────────────────────────

class TestSensors:
    SENSOR_KEY = "simulator-key-change-in-prod"

    def test_ingest_reading(self, client, test_zone):
        resp = client.post(
            "/api/sensors/ingest",
            json={"zone_id": str(test_zone.zone_id), "aqi": 75.5, "pm25": 30.2},
            headers={"X-Sensor-Key": self.SENSOR_KEY},
        )
        assert resp.status_code == 201

    def test_ingest_wrong_key(self, client, test_zone):
        resp = client.post(
            "/api/sensors/ingest",
            json={"zone_id": str(test_zone.zone_id), "aqi": 75.5},
            headers={"X-Sensor-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_latest_all_zones(self, client):
        resp = client.get("/api/sensors/latest")
        assert resp.status_code == 200
        assert isinstance(resp.get_json()["data"], list)

    def test_timeseries(self, client, test_zone):
        resp = client.get(f"/api/sensors/timeseries/{test_zone.zone_id}?hours=24")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "series" in data

    def test_bulk_ingest(self, client, test_zone):
        payload = [
            {"zone_id": str(test_zone.zone_id), "aqi": 80 + i, "pm25": 30.0}
            for i in range(5)
        ]
        resp = client.post(
            "/api/sensors/bulk-ingest",
            json=payload,
            headers={"X-Sensor-Key": self.SENSOR_KEY},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["inserted"] == 5


# ─── Reports ─────────────────────────────────────────────────────────────────

class TestReports:
    def test_list_reports(self, client):
        resp = client.get("/api/reports")
        assert resp.status_code == 200

    def test_submit_report(self, client, test_zone, citizen_token):
        resp = client.post(
            "/api/reports",
            json={
                "zone_id": str(test_zone.zone_id),
                "category": "drain",
                "title": "Open drain near sector park",
                "description": "Large open drain causing mosquito breeding",
                "latitude": 30.9010,
                "longitude": 75.8573,
            },
            headers={"Authorization": f"Bearer {citizen_token}"},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["status"] == "pending"

    def test_submit_report_missing_field(self, client, test_zone, citizen_token):
        resp = client.post(
            "/api/reports",
            json={"zone_id": str(test_zone.zone_id), "category": "drain"},
            headers={"Authorization": f"Bearer {citizen_token}"},
        )
        assert resp.status_code == 400

    def test_upvote_report(self, client, test_zone, citizen_token):
        # First create a report
        create_resp = client.post(
            "/api/reports",
            json={"zone_id": str(test_zone.zone_id), "category": "noise", "title": "Loud factory"},
            headers={"Authorization": f"Bearer {citizen_token}"},
        )
        report_id = create_resp.get_json()["data"]["report_id"]
        # Upvote it
        resp = client.post(
            f"/api/reports/{report_id}/upvote",
            headers={"Authorization": f"Bearer {citizen_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["upvotes"] == 1


# ─── Analytics ───────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_city_summary(self, client):
        resp = client.get("/api/analytics/city-summary")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "total_zones" in data
        assert "active_alerts" in data

    def test_heatmap(self, client):
        resp = client.get("/api/analytics/heatmap")
        assert resp.status_code == 200
        assert "zones" in resp.get_json()["data"]

    def test_leaderboard(self, client):
        resp = client.get("/api/analytics/leaderboard?limit=5")
        assert resp.status_code == 200
        items = resp.get_json()["data"]
        assert isinstance(items, list)

    def test_zone_comparison(self, client):
        resp = client.get("/api/analytics/zone-comparison")
        assert resp.status_code == 200
