from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .day_bounds import today_range
from .models import ClimateLog, Greenhouse, IrrigationCycle, Zone
from .serializers import (
    ClimateLogSerializer,
    GreenhouseSerializer,
    IrrigationCycleSerializer,
    ZoneSerializer,
)


def today_irrigation_cycles(now=None):
    """东八区今日的轮灌 queryset —— 列表过滤与看板统计共用，保证口径一致。"""
    start, end = today_range(now)
    return IrrigationCycle.objects.filter(start_at__gte=start, start_at__lt=end)


class GreenhouseViewSet(viewsets.ModelViewSet):
    queryset = Greenhouse.objects.annotate(zone_count=Count("zones")).all()
    serializer_class = GreenhouseSerializer


class ZoneViewSet(viewsets.ModelViewSet):
    serializer_class = ZoneSerializer

    def get_queryset(self):
        qs = Zone.objects.select_related("greenhouse").all()
        greenhouse_id = self.request.query_params.get("greenhouseId")
        status = self.request.query_params.get("status")
        if greenhouse_id:
            qs = qs.filter(greenhouse_id=greenhouse_id)
        if status:
            qs = qs.filter(status=status)
        return qs


class ClimateLogViewSet(viewsets.ModelViewSet):
    serializer_class = ClimateLogSerializer

    def get_queryset(self):
        qs = ClimateLog.objects.select_related("zone", "zone__greenhouse").all()
        zone_id = self.request.query_params.get("zoneId")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        return qs


class IrrigationCycleViewSet(viewsets.ModelViewSet):
    serializer_class = IrrigationCycleSerializer

    def get_queryset(self):
        qs = IrrigationCycle.objects.select_related("zone", "zone__greenhouse").all()
        zone_id = self.request.query_params.get("zoneId")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        status = self.request.query_params.get("status")
        if status:
            # 归一化空白/大小写，避免脏状态记录被过滤漏掉
            qs = qs.filter(status=IrrigationCycle.normalize_status(status))
        if self.request.query_params.get("today") == "1":
            start, end = today_range()
            qs = qs.filter(start_at__gte=start, start_at__lt=end)
        return qs.order_by("-start_at", "-id")

    def paginate_queryset(self, queryset):
        # 今日集合按天天然有界，返回完整列表，保证前端加总不被分页截断
        if self.request.query_params.get("today") == "1":
            return None
        return super().paginate_queryset(queryset)

    def perform_create(self, serializer):
        # status 已在 validate_status 归一化，model.save 再兜底一次
        serializer.save()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    now = timezone.now()
    since_24h = now - timedelta(hours=24)

    # 今日口径与列表 ?today=1 完全相同（同一归日函数）；
    # 直接对 water_liters 求和，不做任何 join 聚合，也不使用缓存。
    today_cycles = today_irrigation_cycles(now)
    today_liters = today_cycles.aggregate(total=Sum("water_liters"))["total"] or 0

    data = {
        "greenhouseCount": Greenhouse.objects.count(),
        "growingZoneCount": Zone.objects.filter(status=Zone.STATUS_GROWING).count(),
        "climateLogLast24h": ClimateLog.objects.filter(
            recorded_at__gte=since_24h
        ).count(),
        "irrigationScheduledToday": today_cycles.filter(
            status=IrrigationCycle.STATUS_SCHEDULED,
        ).count(),
        "irrigationTodayLiters": today_liters,
    }
    return Response(data)
