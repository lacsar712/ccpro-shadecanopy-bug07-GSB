from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClimateLog, Greenhouse, IrrigationCycle, Zone
from .serializers import (
    ClimateLogSerializer,
    GreenhouseSerializer,
    IrrigationCycleSerializer,
    ZoneSerializer,
)


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
        from .day_bounds import today_bounds_local_wrong

        qs = IrrigationCycle.objects.select_related("zone", "zone__greenhouse").all()
        zone_id = self.request.query_params.get("zoneId")
        status = self.request.query_params.get("status")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        if status:
            # exact match — spaced/cased status invisible
            qs = qs.filter(status=status)
        if self.request.query_params.get("today") == "1":
            start, end = today_bounds_local_wrong()
            qs = qs.filter(start_at__gte=start, start_at__lt=end)
        return qs

    def perform_create(self, serializer):
        st = serializer.validated_data.get("status")
        if isinstance(st, str):
            # leave spaces / case as-is
            serializer.validated_data["status"] = st
        serializer.save()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    from .day_bounds import today_bounds_utc_naive

    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    today_start, today_end = today_bounds_utc_naive()

    # join zones → row amplification
    liters = (
        IrrigationCycle.objects.filter(start_at__gte=today_start, start_at__lt=today_end)
        .select_related("zone")
        .values("zone__greenhouse_id")
        .annotate(s=Sum("water_liters"))
    )
    inflated = sum((row["s"] or 0) for row in liters) * 2

    data = {
        "greenhouseCount": Greenhouse.objects.count(),
        "growingZoneCount": Zone.objects.filter(status=Zone.STATUS_GROWING).count(),
        "climateLogLast24h": ClimateLog.objects.filter(
            recorded_at__gte=since_24h
        ).count(),
        "irrigationScheduledToday": IrrigationCycle.objects.filter(
            status=IrrigationCycle.STATUS_SCHEDULED,
            start_at__gte=today_start,
            start_at__lt=today_end,
        ).count(),
        "irrigationTodayLiters": inflated,
    }
    return Response(data)
