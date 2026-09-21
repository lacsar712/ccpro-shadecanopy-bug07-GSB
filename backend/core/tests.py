from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from .day_bounds import today_range
from .models import Greenhouse, IrrigationCycle, Zone

User = get_user_model()

# 固定“现在”：2026-09-21 12:00 +08:00（04:00 UTC）
FIXED_NOW = timezone.make_aware(datetime(2026, 9, 21, 12, 0), timezone.get_default_timezone())


class DayBoundsTests(APITestCase):
    def test_today_range_is_cst_midnight_in_utc(self):
        start, end = today_range(FIXED_NOW)
        # 东八区 00:00 == 前一日 16:00 UTC
        self.assertEqual(start, datetime(2026, 9, 20, 16, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(end, datetime(2026, 9, 21, 16, 0, tzinfo=dt_timezone.utc))

    def test_utc_timestamp_buckets_by_cst(self):
        # 16:30 UTC == 东八区次日 00:30，必须归到「次日」，而不是 UTC 当日
        start, _ = today_range(FIXED_NOW)
        next_start, next_end = today_range(
            timezone.make_aware(datetime(2026, 9, 21, 16, 30), dt_timezone.utc)
        )
        self.assertTrue(next_start <= datetime(2026, 9, 21, 16, 30, tzinfo=dt_timezone.utc) < next_end)
        self.assertEqual(next_start, start + timedelta(days=1))


class IrrigationAlignmentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="t", password="p")
        self.client.force_authenticate(self.user)
        self.gh = Greenhouse.objects.create(name="GH")
        self.zone = Zone.objects.create(greenhouse=self.gh, zone_code="Z1")

        def cst(hour, minute=0, day=21, liters="0", status="done"):
            return IrrigationCycle.objects.create(
                zone=self.zone,
                start_at=timezone.make_aware(
                    datetime(2026, 9, day, hour, minute),
                    timezone.get_default_timezone(),
                ),
                water_liters=Decimal(liters),
                status=status,
            )

        # 今日（东八区）边界内外各点
        cst(0, 0, liters="10.00")          # 00:00 含
        cst(23, 59, liters="20.50")        # 23:59 含
        cst(8, 0, liters="5.25", status="scheduled")
        cst(0, 0, day=20, liters="999.00")  # 昨日 00:00 不含
        cst(0, 0, day=22, liters="888.00")  # 明日 00:00 不含
        self.expected_today = Decimal("35.75")

    def _dashboard(self):
        return self.client.get(reverse("dashboard")).json()

    def _today_list(self, params=None):
        q = {"today": "1"}
        if params:
            q.update(params)
        return self.client.get(reverse("irrigation-cycle-list"), q).json()

    def test_dashboard_equals_sum_of_today_list(self):
        with mock.patch("django.utils.timezone.now", return_value=FIXED_NOW):
            dash = self._dashboard()
            rows = self._today_list()
        listed = sum(Decimal(str(r["waterLiters"])) for r in rows)
        self.assertEqual(Decimal(str(dash["irrigationTodayLiters"])), self.expected_today)
        self.assertEqual(listed, self.expected_today)
        self.assertEqual(Decimal(str(dash["irrigationTodayLiters"])), listed)
        # 今日列表不分页，共 3 条
        self.assertEqual(len(rows), 3)

    def test_status_filter_uses_same_day_and_normalizes(self):
        with mock.patch("django.utils.timezone.now", return_value=FIXED_NOW):
            rows = self._today_list({"status": " SCHEDULED "})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "scheduled")

    def test_write_with_offset_start_buckets_by_cst(self):
        # 2026-09-21 16:30 UTC == 东八区 09-22 00:30，落在“明日”
        payload = {
            "zoneId": self.zone.id,
            "startAt": "2026-09-21T16:30:00Z",
            "durationMin": 10,
            "waterLiters": "7.00",
            "status": " Running ",
        }
        with mock.patch("django.utils.timezone.now", return_value=FIXED_NOW):
            rsp = self.client.post(reverse("irrigation-cycle-list"), payload, format="json")
            self.assertEqual(rsp.status_code, 201, rsp.content)
            self.assertEqual(rsp.json()["status"], "running")
            dash = self._dashboard()
        # 不计入 09-21 今日
        self.assertEqual(Decimal(str(dash["irrigationTodayLiters"])), self.expected_today)
        cyc = IrrigationCycle.objects.get(id=rsp.json()["id"])
        self.assertEqual(cyc.status, "running")

    def test_after_water_edit_both_sides_still_match(self):
        target = IrrigationCycle.objects.filter(
            status="done", water_liters=Decimal("20.50")
        ).first()
        with mock.patch("django.utils.timezone.now", return_value=FIXED_NOW):
            rsp = self.client.put(
                reverse("irrigation-cycle-detail", args=[target.id]),
                {
                    "zoneId": self.zone.id,
                    "startAt": "2026-09-20T15:59:00Z",  # 09-20 23:59 CST
                    "durationMin": target.duration_min,
                    "waterLiters": "0.00",
                    "status": "done",
                },
                format="json",
            )
            self.assertEqual(rsp.status_code, 200, rsp.content)
            # 改水量/时间后立即重取两侧
            dash = self._dashboard()
            rows = self._today_list()
        listed = sum(Decimal(str(r["waterLiters"])) for r in rows)
        self.assertEqual(Decimal(str(dash["irrigationTodayLiters"])), Decimal("15.25"))
        self.assertEqual(listed, Decimal("15.25"))

    def test_invalid_status_falls_back_to_scheduled(self):
        cyc = IrrigationCycle.objects.create(
            zone=self.zone,
            start_at=FIXED_NOW,
            water_liters=Decimal("1.00"),
            status="  bogus ",
        )
        self.assertEqual(cyc.status, "scheduled")
