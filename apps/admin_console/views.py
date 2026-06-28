"""Admin Console — REST endpoints under /api/v1/admin-console/.

Every endpoint is admin-only (is_staff). Capability level is enforced
per-action inside services via the dual-approval workflow.
"""
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    AdminBanner, AdminExperiment, AdminKpiSnapshot, ApprovalRequest,
    DataExportRequest, FeeSchedule, KillSwitch, LawEnforcementRequest,
    LegalHold, PersonalisationConfig, PlatformAlert, PlatformIncident,
    PlatformSetting, ServiceStatus,
)


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_staff)


def _ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (xff.split(',')[0].strip() if xff
            else request.META.get('REMOTE_ADDR')) or None


# ── CH1 RBAC + approvals ──────────────────────────────────────────────

class MyRoleView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'level': services.admin_level(request.user)})


class ApprovalListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = ApprovalRequest.objects.all()
        st = request.query_params.get('status', 'pending_approval')
        if st:
            qs = qs.filter(status=st)
        return Response({'requests': [
            {'id': r.id, 'kind': r.kind, 'reason': r.reason,
             'submitted_by': r.submitted_by_id, 'status': r.status,
             'target': f'{r.target_type}:{r.target_id}',
             'created_at': r.created_at, 'expires_at': r.expires_at}
            for r in qs[:100]]})


class ApprovalDecisionView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, request_id):
        decision = request.data.get('decision')
        note = request.data.get('note', '')
        if decision == 'approve':
            result = services.approve(request.user, int(request_id), note=note)
        elif decision == 'reject':
            result = services.reject(request.user, int(request_id), note=note)
        else:
            return Response({'error': 'decision must be approve|reject'},
                            status=status.HTTP_400_BAD_REQUEST)
        code = status.HTTP_200_OK if result.get('ok') \
            else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


# ── CH3 commission override ───────────────────────────────────────────

class CommissionOverrideView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        if not services.has_capability(request.user, services.SENIOR_LEVEL):
            return Response({'error': 'senior admin required'},
                            status=status.HTTP_403_FORBIDDEN)
        d = request.data
        req = services.request_commission_override(
            request.user, seller_id=d.get('seller_id'),
            current_rate=d.get('current_rate', 6),
            override_rate=d.get('override_rate'),
            start_date=d.get('start_date'), end_date=d.get('end_date'),
            reason=d.get('reason', ''),
            business_justification=d.get('business_justification', ''))
        return Response({'approval_request_id': req.id, 'status': req.status},
                        status=status.HTTP_201_CREATED)


# ── CH4 personalisation ───────────────────────────────────────────────

class PersonalisationConfigView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        live = PersonalisationConfig.objects.filter(is_live=True).first()
        return Response({'live_version': live.version if live else None,
                         'weights': live.signal_weights if live else {}})

    def post(self, request):
        try:
            cfg = services.create_personalisation_config(
                request.user,
                signal_weights=request.data.get('signal_weights', {}),
                business_rules=request.data.get('business_rules'),
                max_same_seller_per_page=request.data.get(
                    'max_same_seller_per_page', 3),
                min_new_seller_pct=request.data.get('min_new_seller_pct', 10))
        except ValueError as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'version': cfg.version}, status=status.HTTP_201_CREATED)


class PersonalisationDeployView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, config_id):
        result = services.deploy_personalisation_config(
            request.user, int(config_id))
        code = status.HTTP_200_OK if result.get('ok') \
            else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


# ── CH5 experiments ───────────────────────────────────────────────────

class ExperimentView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'experiments': [
            {'id': e.id, 'name': e.name, 'status': e.status,
             'decision': e.decision, 'traffic': e.traffic_allocation_pct}
            for e in AdminExperiment.objects.all()[:100]]})

    def post(self, request):
        exp = services.create_experiment(
            request.user, name=request.data.get('name', 'Experiment'),
            hypothesis=request.data.get('hypothesis', ''),
            variants=request.data.get('variants', []),
            traffic_allocation_pct=request.data.get('traffic_allocation_pct',
                                                    20),
            primary_metric=request.data.get('primary_metric', ''))
        return Response({'id': exp.id}, status=status.HTTP_201_CREATED)


class ExperimentDecisionView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, experiment_id):
        result = services.decide_experiment(
            request.user, int(experiment_id),
            request.data.get('decision', 'continue'),
            note=request.data.get('note', ''))
        code = status.HTTP_200_OK if result.get('ok') \
            else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


# ── CH10 fee schedule ─────────────────────────────────────────────────

class FeeScheduleView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'schedules': [
            {'id': f.id, 'category': f.category_name,
             'current_rate': str(f.current_rate_pct),
             'new_rate': str(f.new_rate_pct),
             'effective_date': f.effective_date, 'status': f.status}
            for f in FeeSchedule.objects.all()[:100]]})

    def post(self, request):
        if not services.has_capability(request.user, services.MIN_APPROVER_LEVEL):
            return Response({'error': 'super admin required'},
                            status=status.HTTP_403_FORBIDDEN)
        d = request.data
        try:
            fs, req = services.schedule_fee_change(
                request.user, category_id=d.get('category_id'),
                category_name=d.get('category_name', ''),
                current_rate=d.get('current_rate'),
                new_rate=d.get('new_rate'),
                effective_date=d.get('effective_date'),
                change_type=d.get('change_type', 'permanent'),
                is_emergency=bool(d.get('is_emergency')),
                reason=d.get('reason', ''))
        except (ValueError, TypeError) as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'fee_schedule_id': fs.id,
                         'approval_request_id': req.id},
                        status=status.HTTP_201_CREATED)


# ── CH13 platform settings + kill switches ────────────────────────────

class PlatformSettingView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'settings': [
            {'key': s.key, 'value': s.value, 'version': s.version}
            for s in PlatformSetting.objects.all()]})

    def post(self, request):
        key = request.data.get('key')
        if not key:
            return Response({'error': 'key required'},
                            status=status.HTTP_400_BAD_REQUEST)
        s = services.set_platform_setting(
            request.user, key, request.data.get('value'),
            description=request.data.get('description', ''))
        return Response({'key': s.key, 'version': s.version},
                        status=status.HTTP_201_CREATED)


class KillSwitchView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'switches': [
            {'key': k.key, 'engaged': k.is_engaged}
            for k in KillSwitch.objects.all()]})

    def post(self, request):
        if not services.has_capability(request.user, services.SENIOR_LEVEL):
            return Response({'error': 'senior admin required'},
                            status=status.HTTP_403_FORBIDDEN)
        req = services.toggle_kill_switch(
            request.user, request.data.get('key'),
            engage=bool(request.data.get('engage', True)),
            reason=request.data.get('reason', ''))
        return Response({'approval_request_id': req.id},
                        status=status.HTTP_201_CREATED)


# ── CH16 data export ──────────────────────────────────────────────────

class DataExportView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        req = services.request_data_export(
            request.user, dataset=request.data.get('dataset', 'gmv_report'),
            reason=request.data.get('reason', ''),
            export_format=request.data.get('format', 'csv'),
            is_dpo=request.data.get('is_dpo', False))
        return Response({'id': req.id, 'status': req.status,
                         'deny_reason': req.deny_reason},
                        status=status.HTTP_201_CREATED)


# ── CH18 legal holds + LE requests ────────────────────────────────────

class LegalHoldView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'holds': [
            {'ref': h.hold_ref, 'subject': f'{h.subject_type}:{h.subject_id}',
             'basis': h.legal_basis, 'status': h.status,
             'expires_at': h.expires_at}
            for h in LegalHold.objects.filter(status='active')[:100]]})

    def post(self, request):
        if not services.has_capability(request.user, services.MIN_APPROVER_LEVEL):
            return Response({'error': 'super admin (legal) required'},
                            status=status.HTTP_403_FORBIDDEN)
        d = request.data
        hold, req = services.place_legal_hold(
            request.user, subject_type=d.get('subject_type', 'seller'),
            subject_id=d.get('subject_id'),
            legal_basis=d.get('legal_basis', 'le_request'),
            scope=d.get('scope', 'all_data'),
            requesting_authority=d.get('requesting_authority', ''),
            case_reference=d.get('case_reference', ''))
        return Response({'hold_ref': hold.hold_ref,
                         'approval_request_id': req.id},
                        status=status.HTTP_201_CREATED)


class LeRequestView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        req = services.intake_le_request(
            request.user,
            request_type=request.data.get('request_type', 'preservation'),
            authority=request.data.get('authority', ''),
            case_reference=request.data.get('case_reference', ''),
            subject_id=request.data.get('subject_id', ''))
        return Response({'request_ref': req.request_ref},
                        status=status.HTTP_201_CREATED)


# ── CH21 banners ──────────────────────────────────────────────────────

class BannerView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'banners': [
            {'id': b.id, 'slot': b.slot, 'headline': b.headline,
             'status': b.status, 'go_live_at': b.go_live_at}
            for b in AdminBanner.objects.all()[:100]]})

    def post(self, request):
        banner = services.submit_banner(
            request.user, slot=request.data.get('slot', 'hero_banner_1'),
            headline=request.data.get('headline', ''),
            subline=request.data.get('subline', ''),
            cta_text=request.data.get('cta_text', ''),
            cta_link=request.data.get('cta_link', ''))
        return Response({'id': banner.id, 'status': banner.status},
                        status=status.HTTP_201_CREATED)


class BannerApproveView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, banner_id):
        result = services.approve_banner(request.user, int(banner_id))
        code = status.HTTP_200_OK if result.get('ok') \
            else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


# ── CH22 platform alerts ──────────────────────────────────────────────

class PlatformAlertView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'alerts': [
            {'id': a.id, 'type': a.alert_type, 'severity': a.severity,
             'status': a.status, 'published_at': a.published_at}
            for a in PlatformAlert.objects.all()[:50]]})

    def post(self, request):
        if not services.has_capability(request.user, services.SENIOR_LEVEL):
            return Response({'error': 'senior admin required'},
                            status=status.HTTP_403_FORBIDDEN)
        alert = services.publish_platform_alert(
            request.user,
            alert_type=request.data.get('alert_type', 'service_disruption'),
            message=request.data.get('message', ''),
            channels=request.data.get('channels', ['in_app']),
            severity=request.data.get('severity', 'high'))
        return Response({'id': alert.id}, status=status.HTTP_201_CREATED)


# ── CH23 service status + incidents ───────────────────────────────────

class ServiceStatusView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'services': [
            {'name': s.service_name, 'state': s.state,
             'latency_p99_ms': s.latency_p99_ms,
             'error_rate_pct': str(s.error_rate_pct)}
            for s in ServiceStatus.objects.all()]})


class IncidentView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'incidents': [
            {'id': i.id, 'title': i.title, 'severity': i.severity,
             'status': i.status, 'started_at': i.started_at}
            for i in PlatformIncident.objects.exclude(status='resolved')[:50]]})

    def post(self, request):
        inc = services.declare_incident(
            request.user, title=request.data.get('title', 'Incident'),
            severity=request.data.get('severity', 'p2'),
            affected_service=request.data.get('affected_service', ''),
            estimated_affected_users=request.data.get(
                'estimated_affected_users', 0))
        return Response({'id': inc.id}, status=status.HTTP_201_CREATED)

    def patch(self, request):
        result = services.update_incident(
            request.user, request.data.get('incident_id'),
            status=request.data.get('status', 'monitoring'),
            note=request.data.get('note', ''))
        code = status.HTTP_200_OK if result.get('ok') \
            else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


# ── CH24 KPI dashboard ────────────────────────────────────────────────

class AdminKpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'snapshots': [
            {'date': s.snapshot_date, 'take_rate_pct': str(s.take_rate_pct),
             'active_experiments': s.active_experiments,
             'pending_approvals': s.pending_approvals,
             'active_incidents': s.active_incidents,
             'carrier_on_time_pct': str(s.carrier_on_time_pct),
             'dual_approval_compliance_pct':
                 str(s.dual_approval_compliance_pct),
             'audit_coverage_pct': str(s.audit_coverage_pct)}
            for s in AdminKpiSnapshot.objects.order_by('-snapshot_date')[:30]]})

    def post(self, request):
        snap = services.snapshot_admin_kpis()
        return Response({'date': snap.snapshot_date},
                        status=status.HTTP_201_CREATED)
