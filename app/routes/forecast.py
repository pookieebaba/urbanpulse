from flask import Blueprint, request
from datetime import datetime
from app import redis_client
from app.models import Zone
from app.services.forecast_service import get_forecast
from app.utils.response import success, error
import json

forecast_bp = Blueprint("forecast", __name__)


@forecast_bp.route("/<zone_id>", methods=["GET"])
def zone_forecast(zone_id):
    zone = Zone.query.get_or_404(zone_id)
    cache_key = f"forecast:{zone_id}"
    cached = redis_client.get(cache_key)

    if cached:
        return success(json.loads(cached))

    forecast = get_forecast(zone_id, hours_ahead=24)
    if forecast is None:
        return error("Insufficient historical data to generate forecast (need ≥14 days)", 422)

    result = {
        "zone_id": zone_id,
        "zone_name": zone.name,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "forecast": forecast,
    }
    redis_client.setex(cache_key, 3600, json.dumps(result))
    return success(result)
