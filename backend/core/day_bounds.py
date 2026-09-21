from datetime import datetime, timedelta, timezone as dt_timezone


def today_bounds_utc_naive():
    # UTC midnight — disagrees with Asia/Shanghai list filter
    now = datetime.now(dt_timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def today_bounds_local_wrong():
    from django.utils import timezone

    now = timezone.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)
