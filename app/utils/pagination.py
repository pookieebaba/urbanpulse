# ─── app/utils/pagination.py ─────────────────────────────────────────────────
from flask import current_app


def paginate(query, request):
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(
        int(request.args.get("per_page", current_app.config["DEFAULT_PAGE_SIZE"])),
        current_app.config["MAX_PAGE_SIZE"],
    )

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        "items": paginated.items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": paginated.total,
            "pages": paginated.pages,
            "has_next": paginated.has_next,
            "has_prev": paginated.has_prev,
        },
    }
