# ─── app/services/gamification_service.py ────────────────────────────────────
from app import db
from app.models import Citizen, CitizenBadge, BadgeType

POINTS_PER_REPORT = 10

BADGE_RULES = [
    (1, BadgeType.FIRST_REPORT),
    (10, BadgeType.TEN_REPORTS),
    (50, BadgeType.FIFTY_REPORTS),
]


def award_points_for_report(citizen: Citizen):
    citizen.points = (citizen.points or 0) + POINTS_PER_REPORT

    total_reports = citizen.reports.count() + 1  # +1 for the report being added
    for threshold, badge_type in BADGE_RULES:
        if total_reports == threshold:
            already = CitizenBadge.query.filter_by(
                citizen_id=citizen.citizen_id,
                badge_type=badge_type,
            ).first()
            if not already:
                badge = CitizenBadge(
                    citizen_id=citizen.citizen_id,
                    badge_type=badge_type,
                )
                db.session.add(badge)
