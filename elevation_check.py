"""Pure helpers for Portal-only DEM elevation checks."""

from math import isfinite
from statistics import median


EH2000 = "eh2000"
BK77 = "bk77"
ELLIPSOIDAL = "ellipsoidal"
UNKNOWN = "unknown"


def finite_height(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def conversion_plan(source, target):
    """Return public MaRu height-model operations for one conversion."""
    source = str(source or UNKNOWN)
    target = str(target or UNKNOWN)
    if source == target or UNKNOWN in {source, target}:
        return ()
    direct = {
        (BK77, EH2000): ("bk77_to_eh2000",),
        (EH2000, BK77): ("eh2000_to_bk77",),
        (ELLIPSOIDAL, EH2000): ("ellipsoidal_to_eh2000",),
        (EH2000, ELLIPSOIDAL): ("eh2000_to_ellipsoidal",),
        (BK77, ELLIPSOIDAL): (
            "bk77_to_eh2000", "eh2000_to_ellipsoidal",
        ),
        (ELLIPSOIDAL, BK77): (
            "ellipsoidal_to_eh2000", "eh2000_to_bk77",
        ),
    }
    return direct.get((source, target), ())


def matching_range(target, tolerance):
    target = finite_height(target)
    tolerance = finite_height(tolerance)
    if target is None or tolerance is None or tolerance <= 0:
        raise ValueError("Target height and a positive tolerance are required.")
    return target - tolerance, target + tolerance


def sample_summary(values):
    """Return robust 3x3 raster statistics, ignoring invalid values."""
    valid = [finite_height(value) for value in values]
    valid = [value for value in valid if value is not None]
    if not valid:
        return None
    return {
        "count": len(valid),
        "median": median(valid),
        "minimum": min(valid),
        "maximum": max(valid),
    }
