"""
AQI forecasting service using Facebook Prophet.
Falls back to a simple moving-average if Prophet is not installed.
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


def get_forecast(zone_id: str, hours_ahead: int = 24) -> Optional[List[Dict]]:
    """
    Returns a list of hourly forecast dicts:
      { timestamp, predicted_aqi, lower_bound, upper_bound }
    Returns None if there is insufficient data.
    """
    from app import db
    from app.models import SensorReading
    from sqlalchemy import func

    # Fetch hourly averages for the past 60 days
    since = datetime.utcnow() - timedelta(days=60)

    rows = db.session.query(
        func.date_trunc("hour", SensorReading.recorded_at).label("ds"),
        func.avg(SensorReading.aqi).label("y"),
    ).filter(
        SensorReading.zone_id == zone_id,
        SensorReading.recorded_at >= since,
    ).group_by("ds").order_by("ds").all()

    if len(rows) < 14 * 24:   # at least 14 days of hourly data
        logger.warning("Insufficient data for zone %s: %d hourly points", zone_id, len(rows))
        return None

    try:
        return _prophet_forecast(rows, hours_ahead)
    except ImportError:
        logger.warning("Prophet not installed — using moving average fallback")
        return _moving_average_forecast(rows, hours_ahead)
    except Exception as exc:
        logger.error("Prophet error for zone %s: %s", zone_id, exc)
        return _moving_average_forecast(rows, hours_ahead)


def _prophet_forecast(rows, hours_ahead: int) -> List[Dict]:
    from prophet import Prophet
    import pandas as pd

    df = pd.DataFrame(
        [(row.ds, float(row.y)) for row in rows],
        columns=["ds", "y"],
    )
    df["ds"] = pd.to_datetime(df["ds"])

    model = Prophet(
        interval_width=0.80,
        daily_seasonality=True,
        weekly_seasonality=True,
        seasonality_mode="additive",
        changepoint_prior_scale=0.05,
    )
    model.fit(df)

    future = model.make_future_dataframe(periods=hours_ahead, freq="H")
    forecast = model.predict(future)

    # Return only the future portion
    now = datetime.utcnow()
    future_rows = forecast[forecast["ds"] > now].tail(hours_ahead)

    return [
        {
            "timestamp": row["ds"].isoformat() + "Z",
            "predicted_aqi": max(0.0, round(float(row["yhat"]), 1)),
            "lower_bound": max(0.0, round(float(row["yhat_lower"]), 1)),
            "upper_bound": max(0.0, round(float(row["yhat_upper"]), 1)),
        }
        for _, row in future_rows.iterrows()
    ]


def _moving_average_forecast(rows, hours_ahead: int) -> List[Dict]:
    """Simple 24-hour rolling mean as a fallback."""
    window = min(24, len(rows))
    values = [float(r.y) for r in rows[-window:]]
    mean_aqi = sum(values) / len(values)
    std_aqi = (sum((v - mean_aqi) ** 2 for v in values) / len(values)) ** 0.5

    now = datetime.utcnow()
    return [
        {
            "timestamp": (now + timedelta(hours=i + 1)).isoformat() + "Z",
            "predicted_aqi": round(mean_aqi, 1),
            "lower_bound": round(max(0.0, mean_aqi - std_aqi), 1),
            "upper_bound": round(mean_aqi + std_aqi, 1),
        }
        for i in range(hours_ahead)
    ]
