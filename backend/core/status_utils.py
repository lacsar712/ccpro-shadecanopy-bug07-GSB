"""轮灌状态读写归一化。

对外对内都只允许四个规范值：
scheduled（已排程）/ running（进行中）/ done（已完成）/ skipped（已跳过）。
空白（None、""、纯空格）归一为 scheduled；容忍大小写、首尾空白与常见别名。
列表过滤与写入保存共用本函数，避免“写得进、查不到”。
"""

from .models import IrrigationCycle

# 别名统一到规范值（键已 strip + lower）。
STATUS_ALIASES = {
    "scheduled": IrrigationCycle.STATUS_SCHEDULED,
    "sched": IrrigationCycle.STATUS_SCHEDULED,
    "pending": IrrigationCycle.STATUS_SCHEDULED,
    "queued": IrrigationCycle.STATUS_SCHEDULED,
    "已排程": IrrigationCycle.STATUS_SCHEDULED,
    "running": IrrigationCycle.STATUS_RUNNING,
    "in_progress": IrrigationCycle.STATUS_RUNNING,
    "in-progress": IrrigationCycle.STATUS_RUNNING,
    "active": IrrigationCycle.STATUS_RUNNING,
    "进行中": IrrigationCycle.STATUS_RUNNING,
    "done": IrrigationCycle.STATUS_DONE,
    "completed": IrrigationCycle.STATUS_DONE,
    "complete": IrrigationCycle.STATUS_DONE,
    "finished": IrrigationCycle.STATUS_DONE,
    "已完成": IrrigationCycle.STATUS_DONE,
    "skipped": IrrigationCycle.STATUS_SKIPPED,
    "skip": IrrigationCycle.STATUS_SKIPPED,
    "canceled": IrrigationCycle.STATUS_SKIPPED,
    "cancelled": IrrigationCycle.STATUS_SKIPPED,
    "已跳过": IrrigationCycle.STATUS_SKIPPED,
}

CANONICAL_STATUSES = {
    IrrigationCycle.STATUS_SCHEDULED,
    IrrigationCycle.STATUS_RUNNING,
    IrrigationCycle.STATUS_DONE,
    IrrigationCycle.STATUS_SKIPPED,
}


class InvalidStatusError(ValueError):
    pass


def normalize_status(value, default=IrrigationCycle.STATUS_SCHEDULED):
    """把任意输入归一为四个规范状态之一。

    空白（None / "" / "  "）→ default（默认 scheduled）。
    无法识别的非空白值抛 InvalidStatusError，拒绝脏数据落库。
    """
    if value is None:
        return default
    if not isinstance(value, str):
        raise InvalidStatusError(f"无法识别的轮灌状态: {value!r}")
    key = value.strip().lower()
    if not key:
        return default
    status = STATUS_ALIASES.get(key)
    if status is None:
        raise InvalidStatusError(f"无法识别的轮灌状态: {value!r}")
    return status
