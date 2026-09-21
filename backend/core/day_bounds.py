from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

# 全系统唯一的“今日”归日时区：列表过滤与仪表盘统计共用，禁止另写口径。
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def today_bounds(now=None):
    """返回东八区自然日 [start, end) 的 UTC 感知边界。

    start_at 以 UTC 存储（USE_TZ=True），因此先在东八区定位当日 0 点，
    再转回 UTC 用于 ORM 过滤；同一函数同时服务列表与统计，保证口径一致。
    """
    if now is None:
        now = datetime.now(SHANGHAI_TZ)
    elif now.tzinfo is None:
        raise ValueError("today_bounds 需要带时区的 datetime")
    else:
        now = now.astimezone(SHANGHAI_TZ)

    start_local = datetime.combine(now.date(), time.min, tzinfo=SHANGHAI_TZ)
    start = start_local.astimezone(ZoneInfo("UTC"))
    return start, start + timedelta(days=1)
