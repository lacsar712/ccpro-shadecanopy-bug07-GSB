"""今日归属与轮灌状态归一化的唯一来源。

列表的「今日」过滤与看板的「今日」统计必须共用这里的函数，
否则两侧会因时区/取日方式不同而对不齐。
"""
from datetime import timedelta

from django.utils import timezone

# 业务日历固定为东八区（UTC+8），不依赖服务器本地时区。
BUSINESS_TZ = timezone.get_default_timezone()  # settings.TIME_ZONE = Asia/Shanghai


def today_range(now=None):
    """返回东八区「今日」的 [起, 止) 边界，均为带时区的 datetime。

    可传入 now（aware datetime）便于测试；返回值直接用于
    DateTimeField 的 start_at__gte/__lt 过滤，Django 会按 UTC 比较。
    """
    if now is None:
        now = timezone.now()
    local = timezone.localtime(now, BUSINESS_TZ)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end
