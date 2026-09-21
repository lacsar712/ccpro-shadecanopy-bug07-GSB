from django.db import migrations


def normalize_statuses(apps, schema_editor):
    """把历史脏状态（空白、带空格、大小写、别名等）清洗为四个规范值。"""
    IrrigationCycle = apps.get_model("core", "IrrigationCycle")
    # 迁移中 apps.get_model 得到的模型与 status_utils 的常量同源语义，
    # 直接复用归一函数；无法识别的非空白值回退为 scheduled。
    from core.status_utils import normalize_status

    for cycle in IrrigationCycle.objects.all():
        try:
            new_status = normalize_status(cycle.status)
        except Exception:
            new_status = "scheduled"
        if new_status != cycle.status:
            cycle.status = new_status
            cycle.save(update_fields=["status", "updated_at"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(normalize_statuses, noop),
    ]
