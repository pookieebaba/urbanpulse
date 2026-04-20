# UrbanPulse — Smart City Environment Platform
### Backend API (Python · Flask · PostgreSQL · Redis · WebSockets)

---

## Project Structure

```
urbanpulse/
├── app/
│   ├── __init__.py          # App factory & extension setup
│   ├── models.py            # SQLAlchemy ORM models
│   ├── routes/
│   │   ├── auth.py          # POST /api/auth/* (register, login, me)
│   │   ├── zones.py         # GET/POST /api/zones/*
│   │   ├── sensors.py       # POST /api/sensors/ingest  GET /api/sensors/*
│   │   ├── alerts.py        # GET /api/alerts/*
│   │   ├── reports.py       # GET/POST /api/reports/*
│   │   ├── analytics.py     # GET /api/analytics/*
│   │   └── forecast.py      # GET /api/forecast/<zone_id>
│   ├── services/
│   │   ├── alert_service.py       # Threshold-based alert engine
│   │   ├── anomaly_service.py     # Z-score anomaly detection
│   │   ├── forecast_service.py    # Prophet / fallback forecasting
│   │   ├── gamification_service.py# Points & badge awards
│   │   └── websocket_service.py   # Socket.IO event handlers
│   └── utils/
│       ├── response.py      # Standardised JSON helpers
│       ├── validators.py    # Email / password validation
│       └── pagination.py    # Reusable paginator
├── scripts/
│   ├── sensor_simulator.py  # IoT data emitter (runs standalone)
│   └── seed_db.py           # Seeds zones + 60 days of historical data
├── tests/
│   └── test_api.py          # Pytest test suite (35+ test cases)
├── config.py                # Dev / Test / Prod config classes
├── run.py                   # Application entry point
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Quick Start — Docker (Recommended)

> One command to spin up the entire stack:

```bash
git clone <your-repo-url> urbanpulse
cd urbanpulse
cp .env.example .env        # edit secrets if needed
docker-compose up --build
```

This will:
1. Start **PostgreSQL** and **Redis** containers
2. Run **database migrations** (`flask db upgrade`)
3. **Seed** 20 city zones + 60 days of hourly sensor history
4. Start the **Flask API** on port 5000
5. Start the **sensor simulator** (emits live readings every 30s)

API is live at: `http://localhost:5000`

---

## Manual Setup (Without Docker)

### Prerequisites
- Python 3.11+
- PostgreSQL 14+ running locally
- Redis 7+ running locally

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
cp .env.example .env
# Edit .env with your local DATABASE_URL and REDIS_URL

# 4. Create the database
createdb urbanpulse_dev

# 5. Run migrations
flask --app run.py db upgrade

# 6. Seed database (zones + historical data ~60 days)
python scripts/seed_db.py

# 7. Start the API
python run.py

# 8. In a second terminal — start the sensor simulator
python scripts/sensor_simulator.py --interval 30
```

### Default Login Credentials (after seeding)
| Role    | Email                          | Password     |
|---------|--------------------------------|--------------|
| Admin   | admin@urbanpulse.city          | Admin@1234   |
| Citizen | citizen@urbanpulse.city        | Demo@1234    |

---

## Running Tests

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

Expected: **35+ tests**, all passing.

---

## API Reference

All responses follow this envelope:

```json
{
  "success": true,
  "data": { ... },
  "message": "OK"
}
```

### Authentication

| Method | Endpoint               | Auth | Description                  |
|--------|------------------------|------|------------------------------|
| POST   | `/api/auth/register`   | —    | Register new citizen         |
| POST   | `/api/auth/login`      | —    | Login, get JWT tokens        |
| POST   | `/api/auth/refresh`    | JWT (refresh) | Get new access token  |
| GET    | `/api/auth/me`         | JWT  | Get own profile + badges     |
| PATCH  | `/api/auth/me`         | JWT  | Update profile / alert prefs |
| PUT    | `/api/auth/me/password`| JWT  | Change password               |

### Zones

| Method | Endpoint                          | Auth  | Description                      |
|--------|-----------------------------------|-------|----------------------------------|
| GET    | `/api/zones`                      | —     | All zones with live AQI (cached) |
| GET    | `/api/zones/<id>`                 | —     | Zone detail + active alert count |
| GET    | `/api/zones/<id>/sensors`         | —     | Paginated sensor history         |
| GET    | `/api/zones/<id>/summary`         | —     | 24-hr aggregated stats           |
| POST   | `/api/zones`                      | Admin | Create new zone                  |
| PATCH  | `/api/zones/<id>`                 | Admin | Update zone metadata             |

### Sensors

| Method | Endpoint                           | Auth        | Description                       |
|--------|------------------------------------|-------------|-----------------------------------|
| POST   | `/api/sensors/ingest`              | Sensor key  | Ingest single reading             |
| POST   | `/api/sensors/bulk-ingest`         | Sensor key  | Ingest up to 50 readings at once  |
| GET    | `/api/sensors/latest`              | —           | Latest reading per zone           |
| GET    | `/api/sensors/timeseries/<zone_id>`| —           | Hourly-avg time series for charts |
| GET    | `/api/sensors/anomalies`           | —           | Recent anomalous readings         |

### Alerts

| Method | Endpoint                   | Auth  | Description           |
|--------|----------------------------|-------|-----------------------|
| GET    | `/api/alerts/active`       | —     | All active alerts     |
| GET    | `/api/alerts`              | —     | Paginated alert history|
| POST   | `/api/alerts/<id>/resolve` | Admin | Mark alert resolved   |

### Reports (Citizen Issue Reporting)

| Method | Endpoint                         | Auth   | Description                  |
|--------|----------------------------------|--------|------------------------------|
| GET    | `/api/reports`                   | —      | List reports (filter by zone)|
| POST   | `/api/reports`                   | JWT    | Submit new issue report      |
| POST   | `/api/reports/<id>/upvote`       | JWT    | Upvote an issue              |
| PATCH  | `/api/reports/<id>/status`       | Admin  | Update report status         |

### Analytics

| Method | Endpoint                          | Auth | Description                     |
|--------|-----------------------------------|------|---------------------------------|
| GET    | `/api/analytics/city-summary`     | —    | City-wide KPIs for dashboard    |
| GET    | `/api/analytics/heatmap`          | —    | Avg AQI per zone for date range |
| GET    | `/api/analytics/zone-comparison`  | —    | All zones ranked by AQI         |
| GET    | `/api/analytics/leaderboard`      | —    | Top citizen reporters           |

### Forecast

| Method | Endpoint               | Auth | Description                          |
|--------|------------------------|------|--------------------------------------|
| GET    | `/api/forecast/<zone_id>`| —  | 24-hour AQI forecast (Prophet model) |

---

## WebSocket Events

Connect to `ws://localhost:5000` using Socket.IO.

### Client → Server

```js
// Subscribe to real-time updates for a zone
socket.emit("subscribe_zone", { zone_id: "..." })

// Unsubscribe
socket.emit("unsubscribe_zone", { zone_id: "..." })

// Subscribe to city-wide alerts
socket.emit("subscribe_alerts")
```

### Server → Client

```js
// Fires every 30s per zone when simulator is running
socket.on("sensor_update", (data) => {
  // { zone_id, zone_name, aqi, aqi_category, is_anomaly, recorded_at }
})

// Fires when AQI crosses a threshold
socket.on("new_alert", (data) => {
  // { alert_id, zone_id, zone_name, severity, aqi_value, message, ... }
})
```

---

## Key Design Decisions

| Decision | Why |
|---|---|
| **Flask + Socket.IO** | Lightweight, easy to run, great for real-time push |
| **SQLAlchemy ORM** | Type-safe queries, migration support, prevents SQL injection |
| **Redis caching** | Zone list & latest readings cached to avoid hammering PostgreSQL on every dashboard load |
| **Z-score anomaly detection** | Simple, interpretable, no extra ML dependency for this feature |
| **Prophet for forecasting** | Handles seasonality and daily/weekly patterns automatically — perfect for AQI |
| **Graceful fallback** | If Prophet isn't installed, forecast falls back to moving average so the app still works |
| **Bulk ingest endpoint** | Simulator sends all 20 zones in one HTTP call instead of 20 — much more efficient |
| **Rate limiting** | Prevents abuse on auth endpoints using Flask-Limiter + Redis |

---

## Technologies Used

| Layer | Technology | Version |
|---|---|---|
| Web framework | Flask | 3.0.3 |
| Real-time | Flask-SocketIO | 5.3.6 |
| Database ORM | Flask-SQLAlchemy | 3.1.1 |
| Migrations | Flask-Migrate (Alembic) | 4.0.7 |
| Authentication | Flask-JWT-Extended | 4.6.0 |
| Caching | Redis | 7.x |
| Database | PostgreSQL | 16.x |
| ML Forecasting | Prophet (Facebook) | 1.1.5 |
| Containerisation | Docker + Compose | latest |
| Testing | Pytest + pytest-cov | 8.2.2 |
