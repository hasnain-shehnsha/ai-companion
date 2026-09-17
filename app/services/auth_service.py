from app.models.user import User, UserTier


def check_premium_entitlement(user: User | None) -> bool:
    """
    Centralized authorization rule for Premium-only capabilities.
    Returns True if the user is authorized to use Premium features.
    """
    if user is None:
        return False
    return user.tier == UserTier.PAID
