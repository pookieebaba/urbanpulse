# ─── app/utils/validators.py ─────────────────────────────────────────────────
import re


def validate_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_password(password: str) -> bool:
    """At least 8 chars with at least one digit."""
    return len(password) >= 8 and any(c.isdigit() for c in password)
