

from datetime import datetime, date


# ---------- HELPER ----------
def convert_datetime_to_iso(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: convert_datetime_to_iso(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_datetime_to_iso(i) for i in obj]
    if hasattr(obj, "__dict__"):
        return convert_datetime_to_iso(obj.__dict__)
    return obj
