# ─── app/utils/response.py ───────────────────────────────────────────────────
from flask import jsonify


def success(data=None, message="OK", status_code=200):
    body = {"success": True}
    if message != "OK":
        body["message"] = message
    if data is not None:
        body["data"] = data
    return jsonify(body), status_code


def error(message: str, status_code: int = 400):
    return jsonify({"success": False, "error": message}), status_code
