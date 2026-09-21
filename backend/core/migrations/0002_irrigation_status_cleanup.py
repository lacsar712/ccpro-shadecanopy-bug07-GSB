from django.db import migrations

VALID_STATUSES = {"scheduled", "running", "done", "skipped"}


def normalize_status(value):
    if not isinstance(value, str):
        return "scheduled"
    value = value.strip().lower()
    return value if value in VALID_STATUSES else "scheduled"


def clean_statuses(apps, schema_editor):
    IrrigationCycle = apps.get_model("core", "IrrigationCycle")
    for cycle in IrrigationCycle.objects.all():
        normalized = normalize_status(cycle.status)
        if normalized != cycle.status:
            cycle.status = normalized
            cycle.save(update_fields=["status", "updated_at"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(clean_statuses, noop),
    ]
