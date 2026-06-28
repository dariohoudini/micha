"""
Mobile App Engineering — domain services.

Chapter → implementation map (doc: AliExpress_Mobile_App_Engineering.docx):
  CH1-3, 5-10, 14-18  frontend patterns (already shipped in frontend/src/:
        navigation+authGate, stores, cartSync, optimistic UI, SmartImage,
        AutoPlayVideo, infinite-scroll hooks, PullToRefresh, appState,
        safe-area CSS, a11y, design-tokens dark mode, i18n/format)
  CH4   record_sync_replay (idempotent replay audit)
  CH11  register_biometric_credential / issue_biometric_challenge /
        verify_biometric_signature / consume_payment_token
  CH13  queue_silent_push / dispatch_silent_pushes
  CH19  ingest_crash (stack-hash grouping + spike check)
  CH20  ingest_event_batch (≤100 events, event_id dedup)
  CH21  experiment_config_payload / record_exposure
  CH22  create_deferred_link / claim_deferred_link
  CH24  register_app_release / ingest_perf_batch / snapshot_mobile_kpis
"""
import base64
import hashlib
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import (
    AppRelease, BiometricChallenge, BiometricCredential,
    BiometricPaymentToken, ClientPerfMetric, CrashEvent, CrashGroup,
    DeferredDeepLink, MobileAnalyticsEvent, MobileEngineeringEvent,
    MobileEventBatch, MobileExperiment, MobileKpiSnapshot,
    OfflineSyncReplay, SilentPushDispatch,
)

CHALLENGE_TTL_MINUTES = 5
PAYMENT_TOKEN_TTL_MINUTES = 10
MAX_CHALLENGE_ATTEMPTS = 3          # then fall back to PIN/password (doc CH11)
DEEPLINK_TTL_DAYS = 14
CRASH_SPIKE_FACTOR = 5              # alert when hourly rate > 5× baseline


# ──────────────────────────────────────────────────────────────────────
# CH11 — Biometric authentication
# ──────────────────────────────────────────────────────────────────────

def register_biometric_credential(user, *, public_key_pem, device_fingerprint,
                                  algorithm='ec_p256', platform='ios',
                                  biometry_type=''):
    """Enroll: store the device's Secure Enclave public key. Re-enrolling
    the same device replaces the key (biometrics changed → old key invalid).
    """
    if algorithm != 'dev_stub':
        _load_public_key(public_key_pem)  # validates PEM early — raises ValueError
    cred, created = BiometricCredential.objects.update_or_create(
        user=user, device_fingerprint=device_fingerprint,
        defaults={
            'public_key_pem': public_key_pem,
            'algorithm': algorithm,
            'platform': platform,
            'biometry_type': biometry_type,
            'status': 'active',
            'revoked_at': None,
        },
    )
    MobileEngineeringEvent.log('biometric_enrolled', actor=user,
                               device=device_fingerprint[:12],
                               algorithm=algorithm, created=created)
    return cred


def issue_biometric_challenge(user, *, purpose='payment', order_ref='',
                              device_fingerprint=''):
    cred = BiometricCredential.objects.filter(
        user=user, status='active',
        **({'device_fingerprint': device_fingerprint} if device_fingerprint else {}),
    ).first()
    challenge = BiometricChallenge.objects.create(
        user=user, credential=cred, purpose=purpose, order_ref=order_ref,
        challenge=secrets.token_hex(32),
        expires_at=timezone.now() + timedelta(minutes=CHALLENGE_TTL_MINUTES),
    )
    MobileEngineeringEvent.log('biometric_challenge_issued', actor=user,
                               purpose=purpose, order_ref=order_ref)
    return challenge


def _load_public_key(pem):
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    try:
        return load_pem_public_key(pem.encode())
    except Exception as exc:
        raise ValueError(f'invalid public key PEM: {exc}')


def _verify_signature(credential, challenge_str, signature_b64):
    """Returns True iff signature is valid for this credential's key."""
    if credential.algorithm == 'dev_stub':
        # Non-production echo: signature = sha256(challenge). Lets the
        # full flow run on web/simulator without Secure Enclave hardware.
        return signature_b64 == hashlib.sha256(challenge_str.encode()).hexdigest()
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding
    try:
        signature = base64.b64decode(signature_b64)
        key = _load_public_key(credential.public_key_pem)
        if credential.algorithm == 'ec_p256':
            key.verify(signature, challenge_str.encode(),
                       ec.ECDSA(hashes.SHA256()))
        else:  # rsa_2048
            key.verify(signature, challenge_str.encode(),
                       padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, ValueError, Exception):
        return False


@transaction.atomic
def verify_biometric_signature(user, *, challenge_value, signature_b64,
                               device_fingerprint=''):
    """Verify the signed challenge; on success mint a one-time payment
    token. After MAX_CHALLENGE_ATTEMPTS failures the challenge dies and
    the client must fall back to PIN/password (doc CH11 fallback flow).
    """
    try:
        challenge = (BiometricChallenge.objects.select_for_update()
                     .get(user=user, challenge=challenge_value))
    except BiometricChallenge.DoesNotExist:
        return {'verified': False, 'reason': 'unknown_challenge'}

    if challenge.status != 'issued':
        return {'verified': False, 'reason': f'challenge_{challenge.status}'}
    if challenge.expires_at < timezone.now():
        challenge.status = 'expired'
        challenge.save(update_fields=['status'])
        return {'verified': False, 'reason': 'challenge_expired'}

    cred = challenge.credential or BiometricCredential.objects.filter(
        user=user, status='active',
        **({'device_fingerprint': device_fingerprint} if device_fingerprint else {}),
    ).first()
    if cred is None or cred.status != 'active':
        return {'verified': False, 'reason': 'no_active_credential'}

    if not _verify_signature(cred, challenge.challenge, signature_b64):
        challenge.attempts += 1
        if challenge.attempts >= MAX_CHALLENGE_ATTEMPTS:
            challenge.status = 'failed'
        challenge.save(update_fields=['attempts', 'status'])
        MobileEngineeringEvent.log('biometric_verify_failed', actor=user,
                                   attempts=challenge.attempts,
                                   fallback=challenge.status == 'failed')
        return {'verified': False, 'reason': 'bad_signature',
                'attempts_left': max(0, MAX_CHALLENGE_ATTEMPTS - challenge.attempts),
                'fallback_to_password': challenge.status == 'failed'}

    challenge.status = 'verified'
    challenge.verified_at = timezone.now()
    challenge.save(update_fields=['status', 'verified_at'])
    cred.last_used_at = timezone.now()
    cred.save(update_fields=['last_used_at'])

    result = {'verified': True}
    if challenge.purpose == 'payment':
        token = BiometricPaymentToken.objects.create(
            user=user, challenge=challenge, order_ref=challenge.order_ref,
            token=secrets.token_hex(32),
            expires_at=timezone.now() + timedelta(minutes=PAYMENT_TOKEN_TTL_MINUTES),
        )
        result['payment_token'] = token.token
    MobileEngineeringEvent.log('biometric_verified', actor=user,
                               purpose=challenge.purpose)
    return result


@transaction.atomic
def consume_payment_token(user, token_value, order_ref=''):
    """One-time use — the payment flow calls this to redeem the token."""
    try:
        token = (BiometricPaymentToken.objects.select_for_update()
                 .get(user=user, token=token_value))
    except BiometricPaymentToken.DoesNotExist:
        return {'valid': False, 'reason': 'unknown_token'}
    if token.consumed:
        return {'valid': False, 'reason': 'already_consumed'}
    if token.expires_at < timezone.now():
        return {'valid': False, 'reason': 'expired'}
    if order_ref and token.order_ref and token.order_ref != order_ref:
        return {'valid': False, 'reason': 'order_mismatch'}
    token.consumed = True
    token.consumed_at = timezone.now()
    token.save(update_fields=['consumed', 'consumed_at'])
    return {'valid': True}


def revoke_biometric(user, device_fingerprint=None):
    qs = BiometricCredential.objects.filter(user=user, status='active')
    if device_fingerprint:
        qs = qs.filter(device_fingerprint=device_fingerprint)
    n = qs.update(status='revoked', revoked_at=timezone.now())
    MobileEngineeringEvent.log('biometric_revoked', actor=user, count=n)
    return n


# ──────────────────────────────────────────────────────────────────────
# CH4 — Offline sync replay audit
# ──────────────────────────────────────────────────────────────────────

def record_sync_replay(user, *, action_type, idempotency_key, status,
                       device_fingerprint='', retry_count=0,
                       conflict_reason='', payload=None, queued_at_client=None):
    """Idempotent by key — a retried report of the same replay returns
    the original row instead of double-counting the KPI.
    """
    existing = OfflineSyncReplay.objects.filter(
        idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    replay = OfflineSyncReplay.objects.create(
        user=user if getattr(user, 'pk', None) else None,
        device_fingerprint=device_fingerprint,
        action_type=action_type if action_type in
        dict(OfflineSyncReplay.ACTION_CHOICES) else 'other',
        idempotency_key=idempotency_key,
        queued_at_client=queued_at_client,
        retry_count=retry_count,
        status=status if status in dict(OfflineSyncReplay.STATUS_CHOICES)
        else 'failed',
        conflict_reason=conflict_reason[:120],
        payload=payload or {},
    )
    MobileEngineeringEvent.log('sync_replay_recorded', actor=user,
                               action=action_type, status=status)
    return replay, True


# ──────────────────────────────────────────────────────────────────────
# CH13 — Silent push
# ──────────────────────────────────────────────────────────────────────

def queue_silent_push(user, *, push_type, data=None):
    dispatch = SilentPushDispatch.objects.create(
        user=user, push_type=push_type, data=data or {})
    MobileEngineeringEvent.log('silent_push_queued', actor=user,
                               push_type=push_type)
    return dispatch


def dispatch_silent_pushes(limit=200):
    """Send queued data-only pushes via the existing push transport.
    Payload carries no title/body → no user-visible notification.
    """
    sent = failed = 0
    for dispatch in SilentPushDispatch.objects.filter(
            status='queued').select_related('user')[:limit]:
        try:
            from apps.notifications.push_service import send_to_user
            summary = send_to_user(
                dispatch.user, title='', body='',
                data={'silent': '1', 'type': dispatch.push_type,
                      **{k: str(v) for k, v in dispatch.data.items()}},
            )
            if summary.get('sent', 0) > 0:
                dispatch.status = 'sent'
                dispatch.devices_sent = summary['sent']
                dispatch.sent_at = timezone.now()
                sent += 1
            else:
                dispatch.status = 'no_devices'
        except Exception as exc:
            dispatch.status = 'failed'
            dispatch.error = str(exc)[:200]
            failed += 1
        dispatch.save(update_fields=['status', 'devices_sent', 'sent_at',
                                     'error'])
    return {'sent': sent, 'failed': failed}


# ──────────────────────────────────────────────────────────────────────
# CH19 — Crash ingest with stack-hash grouping
# ──────────────────────────────────────────────────────────────────────

def _stack_hash(error_type, stack_trace):
    """Group by error type + first 5 normalised frames (file:function,
    line numbers stripped so the same bug across builds groups together).
    """
    frames = []
    for line in (stack_trace or '').splitlines():
        line = line.strip()
        if not line:
            continue
        normalised = ''.join(c for c in line if not c.isdigit())
        frames.append(normalised)
        if len(frames) >= 5:
            break
    return hashlib.sha256(
        (error_type + '|' + '|'.join(frames)).encode()).hexdigest()


@transaction.atomic
def ingest_crash(user, *, error_type, error_message='', stack_trace='',
                 platform='', app_version='', os_version='',
                 device_model='', device_fingerprint='',
                 breadcrumbs=None, context=None, occurred_at=None):
    h = _stack_hash(error_type, stack_trace)
    group, created = CrashGroup.objects.select_for_update().get_or_create(
        stack_hash=h,
        defaults={
            'error_type': error_type[:120],
            'error_message': error_message[:300],
            'platform': platform,
            'first_app_version': app_version,
        },
    )
    if group.status == 'resolved':
        group.status = 'regressed'   # came back in a newer build
    group.events_count += 1
    group.last_app_version = app_version or group.last_app_version
    if user and getattr(user, 'pk', None):
        if not CrashEvent.objects.filter(group=group, user=user).exists():
            group.users_affected += 1
    group.save()

    event = CrashEvent.objects.create(
        group=group,
        user=user if getattr(user, 'pk', None) else None,
        device_fingerprint=device_fingerprint, platform=platform,
        app_version=app_version, os_version=os_version,
        device_model=device_model, stack_trace=stack_trace[:20000],
        breadcrumbs=breadcrumbs or [], context=context or {},
        occurred_at=occurred_at,
    )
    return group, event


def check_crash_spike():
    """Alert when this hour's crash count > CRASH_SPIKE_FACTOR × the
    hourly baseline of the previous 24h (doc CH19 alert rule).
    """
    now = timezone.now()
    hour_count = CrashEvent.objects.filter(
        received_at__gte=now - timedelta(hours=1)).count()
    baseline_total = CrashEvent.objects.filter(
        received_at__gte=now - timedelta(hours=25),
        received_at__lt=now - timedelta(hours=1)).count()
    baseline_hourly = max(1.0, baseline_total / 24.0)
    spiking = hour_count > CRASH_SPIKE_FACTOR * baseline_hourly
    if spiking:
        MobileEngineeringEvent.log('crash_spike_detected',
                                   hour_count=hour_count,
                                   baseline_hourly=round(baseline_hourly, 1))
        try:  # bridge to ops monitoring — fail open if shape differs
            from apps.monitoring.models import Incident
            Incident.objects.create(
                title=f'Mobile crash spike: {hour_count}/h '
                      f'(baseline {baseline_hourly:.1f}/h)',
                severity='high', source='mobile_app.crash_spike')
        except Exception:
            pass
    return {'hour_count': hour_count,
            'baseline_hourly': round(baseline_hourly, 1),
            'spiking': spiking}


# ──────────────────────────────────────────────────────────────────────
# CH20 — Batched analytics ingest
# ──────────────────────────────────────────────────────────────────────

MAX_BATCH_EVENTS = 100


def ingest_event_batch(user, events, *, device_fingerprint=''):
    """Accept up to 100 events; idempotent per event_id so client
    retries after network failures never double-count.
    """
    events = (events or [])[:MAX_BATCH_EVENTS]
    accepted = duplicate = rejected = 0
    # NOTE: validate UUIDs BEFORE the __in lookup — one malformed
    # event_id from the client would otherwise raise ValidationError
    # and reject the whole batch.
    batch_ids = []
    for e in events:
        try:
            batch_ids.append(uuid.UUID(str(e.get('event_id'))))
        except (ValueError, TypeError):
            pass
    seen_ids = set(
        str(u) for u in MobileAnalyticsEvent.objects.filter(
            event_id__in=batch_ids
        ).values_list('event_id', flat=True))
    rows = []
    for e in events:
        try:
            event_id = uuid.UUID(str(e.get('event_id')))
        except (ValueError, TypeError):
            rejected += 1
            continue
        if str(event_id) in seen_ids:
            duplicate += 1
            continue
        seen_ids.add(str(event_id))
        event_time = e.get('event_time')
        try:  # epoch ms (doc schema) or ISO string
            if isinstance(event_time, (int, float)):
                from datetime import timezone as dt_tz
                event_time = timezone.datetime.fromtimestamp(
                    event_time / 1000.0, tz=dt_tz.utc)
            else:
                event_time = timezone.datetime.fromisoformat(str(event_time))
                if timezone.is_naive(event_time):
                    event_time = timezone.make_aware(event_time)
        except (ValueError, TypeError, OSError):
            event_time = timezone.now()
        rows.append(MobileAnalyticsEvent(
            event_id=event_id,
            user=user if getattr(user, 'pk', None) else None,
            session_id=str(e.get('session_id') or '')[:64],
            device_fingerprint=(str(e.get('device_fp') or '')
                                or device_fingerprint)[:64],
            platform=str(e.get('platform') or '')[:12],
            app_version=str(e.get('app_version') or '')[:24],
            os_version=str(e.get('os_version') or '')[:24],
            device_model=str(e.get('device_model') or '')[:64],
            network_type=str(e.get('network_type') or '')[:12],
            locale=str(e.get('locale') or '')[:12],
            ab_variants=e.get('ab_variants') or {},
            event_name=str(e.get('event_name') or 'unknown')[:64],
            event_category=str(e.get('event_category') or '')[:32],
            properties=e.get('properties') or {},
            event_time=event_time,
        ))
        accepted += 1
    MobileAnalyticsEvent.objects.bulk_create(rows, ignore_conflicts=True)
    batch = MobileEventBatch.objects.create(
        user=user if getattr(user, 'pk', None) else None,
        device_fingerprint=device_fingerprint,
        events_received=len(events), events_accepted=accepted,
        events_duplicate=duplicate, events_rejected=rejected,
    )
    return batch


# ──────────────────────────────────────────────────────────────────────
# CH21 — Client-side experiment config + exposure logging
# ──────────────────────────────────────────────────────────────────────

def experiment_config_payload(platform='all'):
    """The exact shape the client SDK caches and evaluates offline."""
    qs = MobileExperiment.objects.filter(status='running')
    if platform in ('ios', 'android'):
        qs = qs.filter(platform__in=('all', platform))
    return {
        'fetched_at': timezone.now().isoformat(),
        'experiments': [
            {
                'id': exp.slug,
                'name': exp.name,
                'traffic_allocation': exp.traffic_allocation,
                'min_app_version': exp.min_app_version,
                'variants': exp.variants,
            }
            for exp in qs
        ],
    }


def record_exposure(user, *, experiment_slug, variant, session_id='',
                    context=None):
    """Bridge mobile exposures into the existing flags exposure table so
    the A/B evaluation jobs (data_analytics.evaluate_ab_test) see them.
    """
    MobileEngineeringEvent.log('experiment_exposure', actor=user,
                               experiment=experiment_slug, variant=variant)
    try:
        from apps.flags.models import ExperimentExposure
        ExperimentExposure.objects.create(
            flag_name=experiment_slug[:80],
            user_id=user.pk if getattr(user, 'pk', None) else None,
            anon_token=session_id[:64],
            variant=str(variant)[:80],
            context=context or {'source': 'mobile_client_sdk'},
        )
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────
# CH22 — Deferred deep links
# ──────────────────────────────────────────────────────────────────────

def create_deferred_link(*, target_path, params=None, campaign='',
                         device_fingerprint=''):
    link = DeferredDeepLink.objects.create(
        token=secrets.token_urlsafe(24),
        device_fingerprint=device_fingerprint,
        target_path=target_path[:300],
        params=params or {},
        campaign=campaign[:80],
        expires_at=timezone.now() + timedelta(days=DEEPLINK_TTL_DAYS),
    )
    MobileEngineeringEvent.log('deferred_link_created',
                               campaign=campaign, target=target_path[:80])
    return link


@transaction.atomic
def claim_deferred_link(user=None, *, token='', device_fingerprint=''):
    """First launch after install: claim by exact token (came through the
    store referrer) or by device fingerprint match (probabilistic).
    """
    qs = DeferredDeepLink.objects.select_for_update().filter(
        status='pending', expires_at__gte=timezone.now())
    link = None
    if token:
        link = qs.filter(token=token).first()
    if link is None and device_fingerprint:
        link = (qs.filter(device_fingerprint=device_fingerprint)
                .order_by('-created_at').first())
    if link is None:
        return None
    link.status = 'claimed'
    link.claimed_by = user if getattr(user, 'pk', None) else None
    link.claimed_at = timezone.now()
    link.save(update_fields=['status', 'claimed_by', 'claimed_at'])
    MobileEngineeringEvent.log('deferred_link_claimed', actor=user,
                               target=link.target_path[:80])
    return link


# ──────────────────────────────────────────────────────────────────────
# CH24 — Releases, perf ingest and the KPI snapshot
# ──────────────────────────────────────────────────────────────────────

def register_app_release(*, platform, version, build_number=1,
                         js_bundle_kb=0, binary_size_mb=0,
                         rollout_pct=100, is_mandatory=False,
                         release_notes=''):
    release, _ = AppRelease.objects.update_or_create(
        platform=platform, version=version, build_number=build_number,
        defaults={
            'js_bundle_kb': js_bundle_kb,
            'binary_size_mb': Decimal(str(binary_size_mb)),
            'rollout_pct': rollout_pct,
            'is_mandatory': is_mandatory,
            'release_notes': release_notes,
        },
    )
    MobileEngineeringEvent.log('app_release_registered',
                               platform=platform, version=version,
                               bundle_kb=js_bundle_kb)
    return release


MAX_PERF_BATCH = 200


def ingest_perf_batch(user, samples, *, device_fingerprint=''):
    valid_metrics = dict(ClientPerfMetric.METRIC_CHOICES)
    rows = []
    for s in (samples or [])[:MAX_PERF_BATCH]:
        metric = str(s.get('metric') or '')
        if metric not in valid_metrics:
            continue
        try:
            value = Decimal(str(s.get('value')))
        except Exception:
            continue
        rows.append(ClientPerfMetric(
            metric=metric, value=value,
            platform=str(s.get('platform') or '')[:12],
            app_version=str(s.get('app_version') or '')[:24],
            device_model=str(s.get('device_model') or '')[:64],
            device_class=str(s.get('device_class') or '')[:8],
            network_type=str(s.get('network_type') or '')[:12],
            screen=str(s.get('screen') or '')[:64],
            user=user if getattr(user, 'pk', None) else None,
            device_fingerprint=device_fingerprint,
        ))
    ClientPerfMetric.objects.bulk_create(rows)
    return len(rows)


def _percentile(values, pct):
    if not values:
        return 0
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round((pct / 100.0) * (len(values) - 1)))))
    return float(values[k])


def snapshot_mobile_kpis(snapshot_date=None):
    """CH24 — compute every KPI in the doc's dashboard table for one day."""
    snapshot_date = snapshot_date or (timezone.now() - timedelta(days=1)).date()
    day_start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time()))
    day_end = day_start + timedelta(days=1)

    day_events = MobileAnalyticsEvent.objects.filter(
        event_time__gte=day_start, event_time__lt=day_end)
    dau = (day_events.exclude(user=None)
           .values('user').distinct().count())
    events_ingested = day_events.count()

    # Cold start p95 + FPS p5 from RUM samples
    perf = ClientPerfMetric.objects.filter(
        recorded_at__gte=day_start, recorded_at__lt=day_end)
    cold_starts = [float(v) for v in perf.filter(
        metric='cold_start_ms').values_list('value', flat=True)]
    fps = [float(v) for v in perf.filter(
        metric='js_fps').values_list('value', flat=True)]

    # API success rate from client-reported counters
    api_ok = perf.filter(metric='api_success').aggregate(
        s=Sum('value'))['s'] or 0
    api_fail = perf.filter(metric='api_failure').aggregate(
        s=Sum('value'))['s'] or 0
    api_total = float(api_ok) + float(api_fail)
    api_success_pct = (float(api_ok) / api_total * 100) if api_total else 0

    # Crash rate = crashes / DAU
    crashes = CrashEvent.objects.filter(
        received_at__gte=day_start, received_at__lt=day_end).count()
    crash_rate = (crashes / dau * 100) if dau else 0

    # Checkout funnel + search→PDP CTR from the event stream
    checkout_started = day_events.filter(event_name='checkout_start').count()
    purchases = day_events.filter(event_name='purchase').count()
    checkout_pct = (purchases / checkout_started * 100) if checkout_started else 0
    searches = day_events.filter(event_name='search_performed').count()
    pdp_from_search = day_events.filter(
        event_name='product_viewed', properties__source='search').count()
    ctr = (pdp_from_search / searches * 100) if searches else 0

    # Biometric success rate
    bio = BiometricChallenge.objects.filter(
        issued_at__gte=day_start, issued_at__lt=day_end).aggregate(
        ok=Count('id', filter=Q(status='verified')),
        bad=Count('id', filter=Q(status='failed')))
    bio_total = bio['ok'] + bio['bad']
    bio_pct = (bio['ok'] / bio_total * 100) if bio_total else 0

    # Offline sync success rate
    sync = OfflineSyncReplay.objects.filter(
        replayed_at__gte=day_start, replayed_at__lt=day_end).aggregate(
        ok=Count('id', filter=Q(status__in=('applied', 'duplicate'))),
        total=Count('id'))
    sync_pct = (sync['ok'] / sync['total'] * 100) if sync['total'] else 0

    snapshot, _ = MobileKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'cold_start_p95_ms': int(_percentile(cold_starts, 95)),
            'js_fps_p5': Decimal(str(round(_percentile(fps, 5), 1))),
            'crash_rate_pct': Decimal(str(round(crash_rate, 3))),
            'api_success_pct': Decimal(str(round(api_success_pct, 2))),
            'checkout_completion_pct': Decimal(str(round(checkout_pct, 2))),
            'search_to_pdp_ctr_pct': Decimal(str(round(ctr, 2))),
            'biometric_success_pct': Decimal(str(round(bio_pct, 2))),
            'offline_sync_success_pct': Decimal(str(round(sync_pct, 2))),
            'dau': dau,
            'events_ingested': events_ingested,
            'crash_groups_open': CrashGroup.objects.filter(
                status__in=('open', 'regressed')).count(),
        },
    )
    MobileEngineeringEvent.log('mobile_kpis_snapshotted',
                               date=str(snapshot_date), dau=dau)
    return snapshot


# ──────────────────────────────────────────────────────────────────────
# Housekeeping
# ──────────────────────────────────────────────────────────────────────

def purge_expired():
    now = timezone.now()
    expired_challenges = BiometricChallenge.objects.filter(
        status='issued', expires_at__lt=now).update(status='expired')
    expired_links = DeferredDeepLink.objects.filter(
        status='pending', expires_at__lt=now).update(status='expired')
    return {'challenges_expired': expired_challenges,
            'links_expired': expired_links}
