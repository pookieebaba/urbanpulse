from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import IssueReport, Citizen, Zone
from app.utils.response import success, error
from app.utils.pagination import paginate
from app.services.gamification_service import award_points_for_report

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("", methods=["GET"])
def list_reports():
    zone_id = request.args.get("zone_id")
    category = request.args.get("category")
    status = request.args.get("status")

    query = IssueReport.query
    if zone_id:
        query = query.filter_by(zone_id=zone_id)
    if category:
        query = query.filter_by(category=category)
    if status:
        query = query.filter_by(status=status)
    query = query.order_by(IssueReport.upvotes.desc(), IssueReport.created_at.desc())

    result = paginate(query, request)
    result["items"] = [r.to_dict(include_reporter=True) for r in result.pop("items", [])]
    return success(result)


@reports_bp.route("", methods=["POST"])
@jwt_required()
def submit_report():
    citizen = Citizen.query.get(get_jwt_identity())
    if not citizen:
        return error("User not found", 404)

    data = request.get_json() or {}
    required = ["zone_id", "category", "title"]
    for f in required:
        if f not in data:
            return error(f"Field '{f}' is required", 400)

    zone = Zone.query.get(data["zone_id"])
    if not zone:
        return error("Zone not found", 404)

    report = IssueReport(
        citizen_id=citizen.citizen_id,
        zone_id=data["zone_id"],
        category=data["category"],
        title=data["title"],
        description=data.get("description"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        image_url=data.get("image_url"),
    )
    db.session.add(report)
    award_points_for_report(citizen)
    db.session.commit()

    return success(report.to_dict(), "Report submitted", 201)


@reports_bp.route("/<report_id>/upvote", methods=["POST"])
@jwt_required()
def upvote_report(report_id):
    report = IssueReport.query.get_or_404(report_id)
    report.upvotes += 1
    db.session.commit()
    return success({"upvotes": report.upvotes})


@reports_bp.route("/<report_id>/status", methods=["PATCH"])
@jwt_required()
def update_status(report_id):
    citizen = Citizen.query.get(get_jwt_identity())
    if not citizen or not citizen.is_admin:
        return error("Admin access required", 403)

    report = IssueReport.query.get_or_404(report_id)
    data = request.get_json() or {}
    valid_statuses = ["pending", "in_progress", "resolved"]
    if data.get("status") not in valid_statuses:
        return error(f"Status must be one of {valid_statuses}", 400)

    report.status = data["status"]
    if data.get("admin_notes"):
        report.admin_notes = data["admin_notes"]
    db.session.commit()

    return success(report.to_dict(), "Status updated")
