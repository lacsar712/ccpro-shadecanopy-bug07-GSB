from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .day_bounds import SHANGHAI_TZ, today_bounds
from .models import Greenhouse, IrrigationCycle, Zone
from .status_utils import InvalidStatusError, normalize_status

UTC = ZoneInfo("UTC")


def today_list_sum():
    """直接按 day_bounds 边界求和，作为独立于视图的第三只眼。"""
    start, end = today_bounds()
    rows = IrrigationCycle.objects.filter(
        start_at__gte=start, start_at__lt=end
    ).values_list("water_liters", flat=True)
    return sum((Decimal(str(v)) for v in rows), Decimal("0"))


class DayBoundsTests(APITestCase):
    def test_bounds_are_shanghai_midnight_as_utc(self):
        # 2026-09-21 17:00 UTC == 2026-09-22 01:00 上海
        now = datetime(2026, 9, 21, 17, 0, tzinfo=UTC)
        start, end = today_bounds(now)
        # 东八区当日 0 点 = 同日 UTC 16:00
        self.assertEqual(start, datetime(2026, 9, 21, 16, 0, tzinfo=UTC))
        self.assertEqual(end, start + timedelta(days=1))
        self.assertEqual(start.astimezone(SHANGHAI_TZ).strftime("%H:%M"), "00:00")
        self.assertEqual(end.astimezone(SHANGHAI_TZ).strftime("%H:%M"), "00:00")

    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError):
            today_bounds(datetime(2026, 9, 21, 12, 0))


class AlignmentApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="tester", password="x")
        cls.gh = Greenhouse.objects.create(name="棚")
        cls.zone = Zone.objects.create(greenhouse=cls.gh, zone_code="Z1")

    def setUp(self):
        self.client.force_authenticate(self.user)

    def _seed(self):
        start, _ = today_bounds()
        IrrigationCycle.objects.bulk_create(
            [
                IrrigationCycle(  # 今日 09:00 上海
                    zone=self.zone, start_at=start + timedelta(hours=9),
                    duration_min=20, water_liters=Decimal("180.00"),
                    status=IrrigationCycle.STATUS_DONE,
                ),
                IrrigationCycle(  # 今日 23:00 上海
                    zone=self.zone, start_at=start + timedelta(hours=23),
                    duration_min=20, water_liters=Decimal("120.50"),
                    status=IrrigationCycle.STATUS_SCHEDULED,
                ),
                IrrigationCycle(  # 昨日 23:30 上海（UTC 可能仍属“今天”，必须排除）
                    zone=self.zone, start_at=start - timedelta(minutes=30),
                    duration_min=20, water_liters=Decimal("999.00"),
                    status=IrrigationCycle.STATUS_DONE,
                ),
                IrrigationCycle(  # 明日 00:30 上海（必须排除）
                    zone=self.zone, start_at=start + timedelta(days=1, minutes=30),
                    duration_min=20, water_liters=Decimal("777.00"),
                    status=IrrigationCycle.STATUS_SCHEDULED,
                ),
            ]
        )

    def _dashboard_liters(self):
        data = self.client.get("/api/dashboard/").json()
        return Decimal(str(data["irrigationTodayLiters"])), data

    def _list_liters(self, params=None):
        data = self.client.get(
            "/api/irrigation-cycles/",
            data={"today": "1", **(params or {})},
        ).json()
        rows = data["results"] if "results" in data else data
        total = sum((Decimal(str(r["waterLiters"])) for r in rows), Decimal("0"))
        return total, rows

    def test_dashboard_equals_today_list_sum(self):
        self._seed()
        list_sum, rows = self._list_liters()
        dash_liters, dash = self._dashboard_liters()
        self.assertEqual(len(rows), 2)
        self.assertEqual(list_sum, Decimal("300.50"))
        self.assertEqual(dash_liters, list_sum)
        # 与独立口径也一致
        self.assertEqual(today_list_sum(), list_sum)
        self.assertEqual(dash["irrigationScheduledToday"], 1)

    def test_edit_water_then_refetch_both_still_aligned(self):
        self._seed()
        before, _ = self._list_liters()
        self.assertEqual(self._dashboard_liters()[0], before)

        target = IrrigationCycle.objects.filter(
            status=IrrigationCycle.STATUS_DONE
        ).first()
        resp = self.client.put(
            f"/api/irrigation-cycles/{target.id}/",
            {
                "zoneId": self.zone.id,
                "startAt": target.start_at.astimezone(UTC).isoformat(),
                "durationMin": target.duration_min,
                "waterLiters": "260.25",
                "status": "done",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        after_list, _ = self._list_liters()
        after_dash, _ = self._dashboard_liters()
        self.assertEqual(after_list, after_dash)
        self.assertEqual(after_list, before - Decimal("180.00") + Decimal("260.25"))

    def test_move_cycle_out_of_today_keeps_alignment(self):
        self._seed()
        start, end = today_bounds()
        # 明确取一条落在今日区间内的记录移到昨日
        target = IrrigationCycle.objects.filter(
            start_at__gte=start, start_at__lt=end
        ).first()
        target.start_at = start - timedelta(hours=5)
        target.save()
        list_sum, rows = self._list_liters()
        self.assertEqual(self._dashboard_liters()[0], list_sum)
        self.assertEqual(len(rows), 1)

    def test_empty_today_is_zero(self):
        list_sum, rows = self._list_liters()
        dash_liters, _ = self._dashboard_liters()
        self.assertEqual(rows, [])
        self.assertEqual(list_sum, Decimal("0"))
        self.assertEqual(dash_liters, Decimal("0"))

    def test_list_filter_with_spaced_status_matches(self):
        self._seed()
        _, rows = self._list_liters({"status": " Done "})
        self.assertTrue(rows)
        self.assertTrue(all(r["status"] == "done" for r in rows))


class StatusNormalizationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="t2", password="x")
        cls.gh = Greenhouse.objects.create(name="棚2")
        cls.zone = Zone.objects.create(greenhouse=cls.gh, zone_code="Z2")

    def setUp(self):
        self.client.force_authenticate(self.user)

    def test_normalize_function(self):
        self.assertEqual(normalize_status(None), "scheduled")
        self.assertEqual(normalize_status("   "), "scheduled")
        self.assertEqual(normalize_status(" Done "), "done")
        self.assertEqual(normalize_status("RUNNING"), "running")
        self.assertEqual(normalize_status("completed"), "done")
        self.assertEqual(normalize_status("已跳过"), "skipped")
        with self.assertRaises(InvalidStatusError):
            normalize_status("bogus")

    def _payload(self, status):
        return {
            "zoneId": self.zone.id,
            "startAt": datetime.now(UTC).isoformat(),
            "durationMin": 10,
            "waterLiters": "10.00",
            "status": status,
        }

    def test_write_spaced_and_blank_status_normalized(self):
        resp = self.client.post(
            "/api/irrigation-cycles/", self._payload("  Running "), format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["status"], "running")
        self.assertEqual(IrrigationCycle.objects.get().status, "running")

        resp = self.client.post(
            "/api/irrigation-cycles/", self._payload("   "), format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["status"], "scheduled")

    def test_invalid_status_rejected(self):
        resp = self.client.post(
            "/api/irrigation-cycles/", self._payload("weird"), format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_data_migration_cleans_dirty_statuses(self):
        # 绕过校验直接落脏数据，模拟历史遗留，再执行迁移的数据清洗函数
        cycle = IrrigationCycle.objects.create(
            zone=self.zone,
            start_at=datetime.now(UTC),
            water_liters=Decimal("1.00"),
            status="scheduled",
        )
        IrrigationCycle.objects.filter(pk=cycle.pk).update(status=" DoNe ")
        IrrigationCycle.objects.create(
            zone=self.zone,
            start_at=datetime.now(UTC),
            water_liters=Decimal("2.00"),
            status="scheduled",
        )

        import importlib

        migration = importlib.import_module(
            "core.migrations.0002_normalize_irrigation_status"
        )
        migration.normalize_statuses(django_apps, None)

        cleaned = list(
            IrrigationCycle.objects.order_by("id").values_list("status", flat=True)
        )
        self.assertEqual(cleaned, ["done", "scheduled"])
