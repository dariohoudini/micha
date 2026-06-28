"""Mobile App Engineering — REST endpoints under /api/v1/mobile/."""
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from . import services
from .models import (
    AppRelease, BiometricCredential, CrashGroup, MobileKpiSnapshot,
)


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_staff)


def _fp(request):
    return (request.headers.get('X-Device-Fingerprint') or '')[:64]


# ── CH11 Biometrics ───────────────────────────────────────────────────

class BiometricRegisterView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        pem = request.data.get('public_key_pem', '')
        fp = request.data.get('device_fingerprint') or _fp(request)
        if not pem or not fp:
            return Response({'error': 'public_key_pem and device_fingerprint required'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            cred = services.register_biometric_credential(
                request.user, public_key_pem=pem, device_fingerprint=fp,
                algorithm=request.data.get('algorithm', 'ec_p256'),
                platform=request.data.get('platform', 'ios'),
                biometry_type=request.data.get('biometry_type', ''),
            )
        except ValueError as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'enrolled': True, 'credential_id': cred.id,
                         'algorithm': cred.algorithm},
                        status=status.HTTP_201_CREATED)


class BiometricChallengeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        challenge = services.issue_biometric_challenge(
            request.user,
            purpose=request.data.get('purpose', 'payment'),
            order_ref=str(request.data.get('order_ref', ''))[:64],
            device_fingerprint=_fp(request),
        )
        return Response({'challenge': challenge.challenge,
                         'expires_at': challenge.expires_at.isoformat()})


class BiometricVerifyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        result = services.verify_biometric_signature(
            request.user,
            challenge_value=str(request.data.get('challenge', '')),
            signature_b64=str(request.data.get('signature', '')),
            device_fingerprint=_fp(request),
        )
        code = status.HTTP_200_OK if result.get('verified') \
            else status.HTTP_401_UNAUTHORIZED
        return Response(result, status=code)


class BiometricStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cred = BiometricCredential.objects.filter(
            user=request.user, status='active',
            device_fingerprint=_fp(request)).first()
        return Response({'enrolled': cred is not None,
                         'biometry_type': cred.biometry_type if cred else None})

    def delete(self, request):
        n = services.revoke_biometric(request.user, _fp(request) or None)
        return Response({'revoked': n})


# ── CH4 Offline sync replay log ───────────────────────────────────────

class SyncReplayView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        replays = request.data.get('replays')
        if replays is None:  # single-replay shape
            replays = [request.data]
        results = []
        for r in replays[:50]:
            if not r.get('idempotency_key'):
                continue
            replay, created = services.record_sync_replay(
                request.user,
                action_type=str(r.get('action_type', 'other')),
                idempotency_key=str(r['idempotency_key'])[:64],
                status=str(r.get('status', 'applied')),
                device_fingerprint=_fp(request),
                retry_count=int(r.get('retry_count') or 0),
                conflict_reason=str(r.get('conflict_reason', '')),
                payload=r.get('payload') or {},
            )
            results.append({'idempotency_key': replay.idempotency_key,
                            'recorded': created})
        return Response({'results': results}, status=status.HTTP_201_CREATED)


# ── CH19 Crash ingest ─────────────────────────────────────────────────

class CrashIngestThrottle(AnonRateThrottle):
    rate = '60/min'


class CrashIngestView(APIView):
    permission_classes = [permissions.AllowAny]  # crashes happen logged out
    throttle_classes = [CrashIngestThrottle]

    def post(self, request):
        error_type = str(request.data.get('error_type', ''))[:120]
        if not error_type:
            return Response({'error': 'error_type required'},
                            status=status.HTTP_400_BAD_REQUEST)
        user = request.user if request.user.is_authenticated else None
        group, event = services.ingest_crash(
            user,
            error_type=error_type,
            error_message=str(request.data.get('error_message', '')),
            stack_trace=str(request.data.get('stack_trace', '')),
            platform=str(request.data.get('platform', ''))[:12],
            app_version=str(request.data.get('app_version', ''))[:24],
            os_version=str(request.data.get('os_version', ''))[:24],
            device_model=str(request.data.get('device_model', ''))[:64],
            device_fingerprint=_fp(request),
            breadcrumbs=request.data.get('breadcrumbs') or [],
            context=request.data.get('context') or {},
        )
        return Response({'group_id': group.id, 'event_id': event.id},
                        status=status.HTTP_201_CREATED)


class CrashGroupListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = CrashGroup.objects.order_by('-last_seen')
        if request.query_params.get('status'):
            qs = qs.filter(status=request.query_params['status'])
        return Response({'groups': [
            {'id': g.id, 'error_type': g.error_type,
             'error_message': g.error_message, 'platform': g.platform,
             'events_count': g.events_count,
             'users_affected': g.users_affected, 'status': g.status,
             'first_seen': g.first_seen, 'last_seen': g.last_seen,
             'last_app_version': g.last_app_version}
            for g in qs[:100]
        ]})

    def patch(self, request):  # resolve / ignore a group
        group_id = request.data.get('group_id')
        new_status = request.data.get('status')
        if new_status not in ('resolved', 'ignored', 'open'):
            return Response({'error': 'status must be resolved|ignored|open'},
                            status=status.HTTP_400_BAD_REQUEST)
        from django.utils import timezone
        updated = CrashGroup.objects.filter(id=group_id).update(
            status=new_status,
            resolved_at=timezone.now() if new_status == 'resolved' else None)
        return Response({'updated': updated})


# ── CH20 Event batch ingest ───────────────────────────────────────────

class EventBatchThrottle(AnonRateThrottle):
    rate = '120/min'


class EventBatchView(APIView):
    permission_classes = [permissions.AllowAny]  # anonymous browse events too
    throttle_classes = [EventBatchThrottle]

    def post(self, request):
        events = request.data.get('events') or []
        if not isinstance(events, list):
            return Response({'error': 'events must be a list'},
                            status=status.HTTP_400_BAD_REQUEST)
        user = request.user if request.user.is_authenticated else None
        batch = services.ingest_event_batch(
            user, events, device_fingerprint=_fp(request))
        return Response({'accepted': batch.events_accepted,
                         'duplicate': batch.events_duplicate,
                         'rejected': batch.events_rejected},
                        status=status.HTTP_201_CREATED)


# ── CH21 Experiment config + exposures ────────────────────────────────

class ExperimentConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(services.experiment_config_payload(
            platform=request.query_params.get('platform', 'all')))


class ExperimentExposureView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        slug = str(request.data.get('experiment_id', ''))[:80]
        variant = str(request.data.get('variant_id', ''))[:80]
        if not slug or not variant:
            return Response({'error': 'experiment_id and variant_id required'},
                            status=status.HTTP_400_BAD_REQUEST)
        user = request.user if request.user.is_authenticated else None
        recorded = services.record_exposure(
            user, experiment_slug=slug, variant=variant,
            session_id=str(request.data.get('session_id', ''))[:64])
        return Response({'recorded': recorded},
                        status=status.HTTP_201_CREATED)


# ── CH22 Deferred deep links ──────────────────────────────────────────

class DeferredLinkCreateView(APIView):
    permission_classes = [IsAdmin]  # marketing/admin mint links

    def post(self, request):
        target = str(request.data.get('target_path', ''))[:300]
        if not target.startswith('/'):
            return Response({'error': 'target_path must be a relative path'},
                            status=status.HTTP_400_BAD_REQUEST)
        link = services.create_deferred_link(
            target_path=target,
            params=request.data.get('params') or {},
            campaign=str(request.data.get('campaign', ''))[:80],
            device_fingerprint=str(
                request.data.get('device_fingerprint', ''))[:64],
        )
        return Response({'token': link.token,
                         'expires_at': link.expires_at.isoformat()},
                        status=status.HTTP_201_CREATED)


class DeferredLinkClaimView(APIView):
    permission_classes = [permissions.AllowAny]  # first launch, pre-login

    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        link = services.claim_deferred_link(
            user,
            token=str(request.data.get('token', ''))[:64],
            device_fingerprint=_fp(request),
        )
        if link is None:
            return Response({'found': False})
        return Response({'found': True, 'target_path': link.target_path,
                         'params': link.params, 'campaign': link.campaign})


# ── CH24 Releases, perf, KPIs ─────────────────────────────────────────

class ReleaseLatestView(APIView):
    permission_classes = [permissions.AllowAny]  # update-prompt check

    def get(self, request):
        platform = request.query_params.get('platform', 'ios')
        release = AppRelease.objects.filter(platform=platform).first()
        if release is None:
            return Response({'found': False})
        return Response({
            'found': True, 'version': release.version,
            'build_number': release.build_number,
            'is_mandatory': release.is_mandatory,
            'rollout_pct': release.rollout_pct,
            'release_notes': release.release_notes,
        })


class ReleaseRegisterView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        release = services.register_app_release(
            platform=str(request.data.get('platform', 'ios'))[:12],
            version=str(request.data.get('version', ''))[:24],
            build_number=int(request.data.get('build_number') or 1),
            js_bundle_kb=int(request.data.get('js_bundle_kb') or 0),
            binary_size_mb=request.data.get('binary_size_mb') or 0,
            rollout_pct=int(request.data.get('rollout_pct') or 100),
            is_mandatory=bool(request.data.get('is_mandatory')),
            release_notes=str(request.data.get('release_notes', '')),
        )
        return Response({'id': release.id}, status=status.HTTP_201_CREATED)


class PerfBatchView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [EventBatchThrottle]

    def post(self, request):
        samples = request.data.get('samples') or []
        if not isinstance(samples, list):
            return Response({'error': 'samples must be a list'},
                            status=status.HTTP_400_BAD_REQUEST)
        user = request.user if request.user.is_authenticated else None
        n = services.ingest_perf_batch(
            user, samples, device_fingerprint=_fp(request))
        return Response({'accepted': n}, status=status.HTTP_201_CREATED)


class MobileKpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'snapshots': [
            {'date': s.snapshot_date,
             'cold_start_p95_ms': s.cold_start_p95_ms,
             'js_fps_p5': s.js_fps_p5,
             'crash_rate_pct': s.crash_rate_pct,
             'api_success_pct': s.api_success_pct,
             'checkout_completion_pct': s.checkout_completion_pct,
             'search_to_pdp_ctr_pct': s.search_to_pdp_ctr_pct,
             'biometric_success_pct': s.biometric_success_pct,
             'offline_sync_success_pct': s.offline_sync_success_pct,
             'dau': s.dau, 'events_ingested': s.events_ingested,
             'crash_groups_open': s.crash_groups_open}
            for s in MobileKpiSnapshot.objects.order_by('-snapshot_date')[:30]
        ]})

    def post(self, request):  # recompute on demand
        snapshot = services.snapshot_mobile_kpis()
        return Response({'date': snapshot.snapshot_date,
                         'dau': snapshot.dau},
                        status=status.HTTP_201_CREATED)
