from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .day_bounds import today_bounds
from .models import ClimateLog, Greenhouse, IrrigationCycle, Zone
from .serializers import (
    ClimateLogSerializer,
    GreenhouseSerializer,
    IrrigationCycleSerializer,
    ZoneSerializer,
)
from .status_utils import InvalidStatusError, normalize_status


def today_cycles():
    """今日轮灌的唯一 queryset 来源。

    列表 today=1 过滤与仪表盘统计都调用本函数，共用同一个东八区归日
    （today_bounds）与同一批行，因此列表水量加总必然等于仪表盘今日升数。
    """
    start, end = today_bounds()
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
        status = self.request.query_params.get("status")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        if status:
            # 与写入同一归一函数：含空白/大小写/别名也能正确过滤
            try:
                status = normalize_status(status)
            except InvalidStatusError:
                qs = qs.none()
            else:
                qs = qs.filter(status=status)
        if self.request.query_params.get("today") == "1":
            # 与仪表盘统计同一归日函数、同一 queryset
            start, end = today_bounds()
            qs = qs.filter(start_at__gte=start, start_at__lt=end)
        return qs


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    now = timezone.now()
    since_24h = now - timedelta(hours=24)

    # 今日轮灌只从共享 queryset 取，保证与列表 today=1 完全同批行。
    today_qs = today_cycles()

    # 单次聚合，无 join、无乘倍、不读缓存：结果恒等于列表 water_liters 加总。
    liters = today_qs.aggregate(total=Sum("water_liters"))["total"] or Decimal("0")

    data = {
        "greenhouseCount": Greenhouse.objects.count(),
        "growingZoneCount": Zone.objects.filter(status=Zone.STATUS_GROWING).count(),
        "climateLogLast24h": ClimateLog.objects.filter(
            recorded_at__gte=since_24h
        ).count(),
        "irrigationScheduledToday": today_qs.filter(
            status=IrrigationCycle.STATUS_SCHEDULED
        ).count(),
        "irrigationTodayLiters": liters,
    }
    return Response(data)
