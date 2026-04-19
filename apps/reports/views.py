from rest_framework import generics, permissions
from .models import Report
from .serializers import ReportSerializer
from apps.users.permissions import IsNotSuspended, IsAdminOrSuperuser


class ReportCreateView(generics.CreateAPIView):
    """POST /api/reports/create/ — Report a product or seller."""
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]


class AdminReportListView(generics.ListAPIView):
    """GET /api/reports/admin/ — All reports, filterable by status/type."""
    serializer_class = ReportSerializer
    permission_classes = [IsAdminOrSuperuser]

    def get_queryset(self):
        qs = Report.objects.all().order_by('-created_at')
        status_filter = self.request.query_params.get('status')
        target_type = self.request.query_params.get('target_type')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if target_type:
            qs = qs.filter(target_type=target_type)
        return qs


class AdminReportUpdateView(generics.UpdateAPIView):
    """PATCH /api/reports/admin/<pk>/ — Mark report reviewed/actioned."""
    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    permission_classes = [IsAdminOrSuperuser]
