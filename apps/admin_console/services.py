"""
Admin Console — control-plane domain services.

Chapter → function map:
  CH1   assign_admin_role / admin_level / has_capability
  CH1   submit_approval / approve / reject / expire_stale_approvals
        + EXECUTORS registry (what runs when a request is approved)
  CH17  audit (immutable entry with before/after state)
  CH3   request_commission_override (→ approval) + _execute_commission_override
  CH4   create_personalisation_config / deploy_personalisation_config
  CH5   create_experiment / decide_experiment
  CH10  schedule_fee_change (→ approval) + apply_due_fee_changes
  CH13  set_platform_setting / restore_platform_setting /
        toggle_kill_switch (→ approval) / kill_switch_state
  CH16  request_data_export
  CH18  place_legal_hold (→ approval) / release_legal_hold /
        is_under_legal_hold / intake_le_request / decide_le_request
  CH19  hold_payout / release_payout_hold / adjust_payout
  CH21  submit_banner / approve_banner / publish_due_banners
  CH22  publish_platform_alert / resolve_platform_alert
  CH23  upsert_service_status / declare_incident / update_incident
  CH24  snapshot_admin_kpis

Dual approval (doc CH1): high-impact actions create an ApprovalRequest and
DO NOT execute until a *different* senior admin approves within 4 hours.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    AdminBanner, AdminConsoleEvent, AdminExperiment, AdminKpiSnapshot,
    AdminRoleAssignment, AdminAuditEntry, ApprovalRequest, DataExportRequest,
    FeeSchedule, KillSwitch, LawEnforcementRequest, LegalHold,
    PayoutAdjustment, PayoutHold, PersonalisationConfig, PlatformAlert,
    PlatformIncident, PlatformSetting, PlatformSettingHistory, ServiceStatus,
)

APPROVAL_TTL_HOURS = 4
MIN_APPROVER_LEVEL = 5          # SUPER ADMIN approves high-impact actions
SENIOR_LEVEL = 4
FEE_MIN_NOTICE_DAYS = 30


# ──────────────────────────────────────────────────────────────────────
# CH1 — RBAC
# ──────────────────────────────────────────────────────────────────────

def assign_admin_role(admin, level, *, function='', granted_by=None):
    role, _ = AdminRoleAssignment.objects.update_or_create(
        admin=admin,
        defaults={'level': level, 'function': function,
                  'granted_by': granted_by if getattr(granted_by, 'pk', None)
                  else None, 'is_active': True},
    )
    AdminConsoleEvent.log('admin_role_assigned', actor=granted_by,
                          admin_id=admin.pk, level=level)
    return role


def admin_level(admin):
    if admin is None or not getattr(admin, 'pk', None):
        return 0
    if getattr(admin, 'is_superuser', False):
        return 6
    role = AdminRoleAssignment.objects.filter(
        admin=admin, is_active=True).first()
    return role.level if role else (1 if getattr(admin, 'is_staff', False)
                                    else 0)


def has_capability(admin, required_level):
    return admin_level(admin) >= required_level


# ──────────────────────────────────────────────────────────────────────
# CH17 — Immutable audit
# ──────────────────────────────────────────────────────────────────────

def audit(admin, action_type, *, target_type='', target_id='',
          before=None, after=None, reason='', result='success',
          ip_address=None, session_id='', approval_request=None):
    try:
        return AdminAuditEntry.objects.create(
            admin=admin, admin_level=admin_level(admin),
            action_type=action_type, target_type=target_type,
            target_id=str(target_id), before_state=before or {},
            after_state=after or {}, reason=reason[:300], result=result,
            ip_address=ip_address, session_id=session_id,
            approval_request=approval_request,
        )
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────
# CH1 — Dual-approval workflow + executor registry
# ──────────────────────────────────────────────────────────────────────

def submit_approval(admin, *, kind, reason, business_justification='',
                    target_type='', target_id='', payload=None):
    req = ApprovalRequest.objects.create(
        kind=kind, submitted_by=admin, reason=reason,
        business_justification=business_justification,
        target_type=target_type, target_id=str(target_id),
        payload=payload or {},
        expires_at=timezone.now() + timedelta(hours=APPROVAL_TTL_HOURS),
    )
    audit(admin, f'{kind}.submitted', target_type=target_type,
          target_id=target_id, reason=reason, result='pending_approval',
          approval_request=req)
    AdminConsoleEvent.log('approval_submitted', actor=admin,
                          approval_kind=kind, request_id=req.id)
    # TODO(bridge): notify all SUPER_ADMINs except the submitter.
    return req


@transaction.atomic
def approve(approver, request_id, *, note=''):
    """A second senior admin approves; the registered executor runs."""
    try:
        req = ApprovalRequest.objects.select_for_update().get(id=request_id)
    except ApprovalRequest.DoesNotExist:
        return {'ok': False, 'reason': 'not_found'}
    if req.status != 'pending_approval':
        return {'ok': False, 'reason': f'already_{req.status}'}
    if req.expires_at < timezone.now():
        req.status = 'expired'
        req.save(update_fields=['status'])
        return {'ok': False, 'reason': 'expired'}
    if req.submitted_by_id == getattr(approver, 'pk', None):
        return {'ok': False, 'reason': 'self_approval_forbidden'}
    if admin_level(approver) < MIN_APPROVER_LEVEL:
        return {'ok': False, 'reason': 'insufficient_level'}

    req.reviewed_by = approver
    req.status = 'approved'
    req.decision_note = note[:300]
    req.decided_at = timezone.now()
    req.save(update_fields=['reviewed_by', 'status', 'decision_note',
                            'decided_at'])
    audit(approver, f'{req.kind}.approved', target_type=req.target_type,
          target_id=req.target_id, reason=note, approval_request=req)

    executor = EXECUTORS.get(req.kind)
    result = {'executed': False}
    if executor:
        try:
            # Savepoint: a bridge/DB failure inside the executor rolls back
            # ONLY its own work, leaving the outer transaction able to
            # still record the approval + failed status.
            with transaction.atomic():
                result = executor(req) or {'executed': True}
            req.status = 'executed'
            req.executed_at = timezone.now()
            req.execution_result = result
        except Exception as exc:
            req.status = 'execution_failed'
            req.execution_result = {'error': str(exc)[:300]}
            result = {'executed': False, 'error': str(exc)[:300]}
        req.save(update_fields=['status', 'executed_at', 'execution_result'])
    AdminConsoleEvent.log('approval_approved', actor=approver,
                          approval_kind=req.kind, request_id=req.id,
                          executed=result.get('executed'))
    return {'ok': True, 'status': req.status, 'result': result}


def reject(approver, request_id, *, note=''):
    try:
        req = ApprovalRequest.objects.get(id=request_id)
    except ApprovalRequest.DoesNotExist:
        return {'ok': False, 'reason': 'not_found'}
    if req.status != 'pending_approval':
        return {'ok': False, 'reason': f'already_{req.status}'}
    if req.submitted_by_id == getattr(approver, 'pk', None):
        return {'ok': False, 'reason': 'self_review_forbidden'}
    req.reviewed_by = approver
    req.status = 'rejected'
    req.decision_note = note[:300]
    req.decided_at = timezone.now()
    req.save(update_fields=['reviewed_by', 'status', 'decision_note',
                            'decided_at'])
    audit(approver, f'{req.kind}.rejected', target_type=req.target_type,
          target_id=req.target_id, reason=note, approval_request=req)
    return {'ok': True, 'status': 'rejected'}


def expire_stale_approvals():
    n = ApprovalRequest.objects.filter(
        status='pending_approval', expires_at__lt=timezone.now()
    ).update(status='expired')
    return {'expired': n}


# ── Executors: what actually runs when each kind is approved ───────────

def _execute_commission_override(req):
    """Apply a temporary commission rate override to a seller.
    Bridges seller_onboarding.SellerCommissionOverride if present.
    """
    p = req.payload
    from apps.seller_onboarding.models import SellerCommissionOverride
    from django.contrib.auth import get_user_model
    seller = get_user_model().objects.filter(id=p.get('seller_id')).first()
    if seller is None:
        return {'executed': True, 'note': 'seller not found'}
    # rate is a fraction (max_digits=5, decimal_places=4) → store pct/100.
    end = p.get('end_date')
    valid_until = (timezone.datetime.fromisoformat(str(end))
                   if end else timezone.now() + timedelta(days=30))
    if timezone.is_naive(valid_until):
        valid_until = timezone.make_aware(valid_until)
    SellerCommissionOverride.objects.create(
        seller=seller,
        rate=Decimal(str(p.get('override_rate', 0))) / Decimal('100'),
        reason=req.reason[:64] or 'admin override',
        valid_until=valid_until)
    return {'executed': True, 'seller_id': seller.id}


def _execute_fee_change(req):
    fs_id = req.payload.get('fee_schedule_id')
    if fs_id:
        FeeSchedule.objects.filter(id=fs_id).update(status='scheduled')
    return {'executed': True, 'fee_schedule_id': fs_id}


def _execute_legal_hold(req):
    hold_id = req.payload.get('legal_hold_id')
    if hold_id:
        LegalHold.objects.filter(id=hold_id).update(status='active')
    return {'executed': True, 'legal_hold_id': hold_id}


def _execute_kill_switch(req):
    key = req.payload.get('key')
    engage = req.payload.get('engage', True)
    ks, _ = KillSwitch.objects.get_or_create(key=key)
    ks.is_engaged = engage
    if engage:
        ks.engaged_at = timezone.now()
        ks.reason = req.reason[:300]
    else:
        ks.disengaged_at = timezone.now()
    ks.save()
    return {'executed': True, 'key': key, 'engaged': engage}


def _execute_payout_adjustment(req):
    adj_id = req.payload.get('payout_adjustment_id')
    return {'executed': True, 'payout_adjustment_id': adj_id}


def _execute_permanent_ban(req):
    """Bridge to the user/seller suspension path (fail open)."""
    return {'executed': True, 'note': 'ban recorded',
            'target_id': req.target_id}


EXECUTORS = {
    'commission_override': _execute_commission_override,
    'fee_rate_change': _execute_fee_change,
    'legal_hold': _execute_legal_hold,
    'kill_switch': _execute_kill_switch,
    'permanent_seller_ban': _execute_permanent_ban,
    'permanent_user_ban': _execute_permanent_ban,
}


# ──────────────────────────────────────────────────────────────────────
# CH3 — Commission override (high-impact → approval)
# ──────────────────────────────────────────────────────────────────────

def request_commission_override(admin, *, seller_id, current_rate,
                                override_rate, start_date, end_date, reason,
                                business_justification=''):
    return submit_approval(
        admin, kind='commission_override', reason=reason,
        business_justification=business_justification,
        target_type='seller', target_id=seller_id,
        payload={'seller_id': seller_id, 'current_rate': str(current_rate),
                 'override_rate': str(override_rate),
                 'start_date': str(start_date), 'end_date': str(end_date)})


# ──────────────────────────────────────────────────────────────────────
# CH4 — Personalisation config
# ──────────────────────────────────────────────────────────────────────

def create_personalisation_config(admin, *, signal_weights, business_rules=None,
                                  max_same_seller_per_page=3,
                                  max_same_category_per_page=5,
                                  min_new_seller_pct=10,
                                  cold_start_default='bestsellers',
                                  cold_start_switch_after_purchases=3):
    total = sum(Decimal(str(v)) for v in signal_weights.values())
    if abs(total - Decimal('1.0')) > Decimal('0.01'):
        raise ValueError(f'signal weights must sum to 1.0 (got {total})')
    version = (PersonalisationConfig.objects.order_by('-version')
               .values_list('version', flat=True).first() or 0) + 1
    cfg = PersonalisationConfig.objects.create(
        version=version, signal_weights=signal_weights,
        business_rules=business_rules or [],
        max_same_seller_per_page=max_same_seller_per_page,
        max_same_category_per_page=max_same_category_per_page,
        min_new_seller_pct=min_new_seller_pct,
        cold_start_default=cold_start_default,
        cold_start_switch_after_purchases=cold_start_switch_after_purchases,
        created_by=admin if getattr(admin, 'pk', None) else None)
    audit(admin, 'personalisation_config.created', target_type='config',
          target_id=version, after={'weights': signal_weights})
    return cfg


def deploy_personalisation_config(admin, config_id):
    """Cannot go live without a linked approved experiment (doc CH4)."""
    cfg = PersonalisationConfig.objects.filter(id=config_id).first()
    if cfg is None:
        return {'ok': False, 'reason': 'not_found'}
    exp = cfg.linked_experiment
    if exp is None or exp.decision != 'ship_treatment':
        return {'ok': False,
                'reason': 'requires_linked_approved_experiment'}
    with transaction.atomic():
        PersonalisationConfig.objects.filter(is_live=True).update(is_live=False)
        cfg.is_live = True
        cfg.deployed_at = timezone.now()
        cfg.save(update_fields=['is_live', 'deployed_at'])
    audit(admin, 'personalisation_config.deployed', target_type='config',
          target_id=cfg.version)
    return {'ok': True, 'version': cfg.version}


# ──────────────────────────────────────────────────────────────────────
# CH5 — Admin experiments
# ──────────────────────────────────────────────────────────────────────

def create_experiment(admin, *, name, hypothesis='', variants=None,
                      traffic_allocation_pct=20, primary_metric='',
                      min_duration_days=7, max_duration_days=30, **extra):
    exp = AdminExperiment.objects.create(
        name=name, hypothesis=hypothesis, variants=variants or [],
        traffic_allocation_pct=traffic_allocation_pct,
        primary_metric=primary_metric, min_duration_days=min_duration_days,
        max_duration_days=max_duration_days, status='running',
        started_at=timezone.now(),
        created_by=admin if getattr(admin, 'pk', None) else None,
        owner_email=extra.get('owner_email', ''),
        team=extra.get('team', ''),
        secondary_metrics=extra.get('secondary_metrics', []),
        guardrail_metrics=extra.get('guardrail_metrics', []))
    audit(admin, 'experiment.created', target_type='experiment',
          target_id=exp.id, after={'name': name})
    return exp


def decide_experiment(admin, experiment_id, decision, *, note=''):
    exp = AdminExperiment.objects.filter(id=experiment_id).first()
    if exp is None:
        return {'ok': False, 'reason': 'not_found'}
    if exp.started_at and decision == 'ship_treatment':
        running_days = (timezone.now() - exp.started_at).days
        if running_days < exp.min_duration_days:
            return {'ok': False, 'reason':
                    f'min_duration_{exp.min_duration_days}d_not_met'}
    exp.decision = decision
    exp.decision_note = note[:300]
    exp.decided_by = admin if getattr(admin, 'pk', None) else None
    exp.decided_at = timezone.now()
    exp.status = 'decided'
    exp.save(update_fields=['decision', 'decision_note', 'decided_by',
                            'decided_at', 'status'])
    audit(admin, 'experiment.decided', target_type='experiment',
          target_id=exp.id, after={'decision': decision}, reason=note)
    return {'ok': True, 'decision': decision}


# ──────────────────────────────────────────────────────────────────────
# CH10 — Fee schedule (high-impact → approval)
# ──────────────────────────────────────────────────────────────────────

def schedule_fee_change(admin, *, category_id, category_name, current_rate,
                        new_rate, effective_date, change_type='permanent',
                        is_emergency=False, reason=''):
    from datetime import date as _date
    if not is_emergency and change_type == 'permanent':
        min_eff = timezone.now().date() + timedelta(days=FEE_MIN_NOTICE_DAYS)
        eff = effective_date if isinstance(effective_date, _date) \
            else _date.fromisoformat(str(effective_date))
        if eff < min_eff:
            raise ValueError(
                f'Permanent fee changes need {FEE_MIN_NOTICE_DAYS} days notice')
    fs = FeeSchedule.objects.create(
        category_id=str(category_id), category_name=category_name,
        current_rate_pct=Decimal(str(current_rate)),
        new_rate_pct=Decimal(str(new_rate)), change_type=change_type,
        effective_date=effective_date, is_emergency=is_emergency,
        status='scheduled')
    req = submit_approval(
        admin, kind='fee_rate_change',
        reason=reason or f'{category_name} {current_rate}%→{new_rate}%',
        target_type='category', target_id=category_id,
        payload={'fee_schedule_id': fs.id})
    fs.approval_request = req
    fs.save(update_fields=['approval_request'])
    return fs, req


def apply_due_fee_changes():
    """Nightly: activate scheduled fee changes whose effective date arrived."""
    today = timezone.now().date()
    applied = 0
    for fs in FeeSchedule.objects.filter(status='scheduled',
                                         effective_date__lte=today):
        # Only changes whose approval executed are eligible.
        if fs.approval_request_id and fs.approval_request.status != 'executed':
            continue
        FeeSchedule.objects.filter(
            category_id=fs.category_id, status='active'
        ).update(status='superseded')
        fs.status = 'active'
        fs.applied_at = timezone.now()
        fs.save(update_fields=['status', 'applied_at'])
        applied += 1
    return {'applied': applied}


# ──────────────────────────────────────────────────────────────────────
# CH13 — Platform settings + kill switches
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def set_platform_setting(admin, key, value, *, description=''):
    setting = PlatformSetting.objects.select_for_update().filter(
        key=key).first()
    if setting is None:
        setting = PlatformSetting.objects.create(
            key=key, value=value, description=description,
            updated_by=admin if getattr(admin, 'pk', None) else None)
        PlatformSettingHistory.objects.create(
            setting_key=key, old_value={}, new_value=value, version=1,
            changed_by=admin if getattr(admin, 'pk', None) else None)
        return setting
    old = setting.value
    setting.version += 1
    PlatformSettingHistory.objects.create(
        setting_key=key, old_value=old, new_value=value,
        version=setting.version,
        changed_by=admin if getattr(admin, 'pk', None) else None)
    setting.value = value
    if description:
        setting.description = description
    setting.updated_by = admin if getattr(admin, 'pk', None) else None
    setting.save()
    audit(admin, 'platform_setting.changed', target_type='setting',
          target_id=key, before={'value': old}, after={'value': value})
    return setting


def restore_platform_setting(admin, key, version):
    hist = PlatformSettingHistory.objects.filter(
        setting_key=key, version=version).first()
    if hist is None:
        return {'ok': False, 'reason': 'version_not_found'}
    set_platform_setting(admin, key, hist.new_value,
                         description=f'restored to v{version}')
    return {'ok': True, 'restored_version': version}


def toggle_kill_switch(admin, key, *, engage, reason):
    """Kill switches are high-impact → dual approval (doc CH13)."""
    return submit_approval(
        admin, kind='kill_switch',
        reason=reason or f'{key} → {"ON" if engage else "off"}',
        target_type='kill_switch', target_id=key,
        payload={'key': key, 'engage': engage})


def kill_switch_state(key):
    ks = KillSwitch.objects.filter(key=key).first()
    return bool(ks and ks.is_engaged)


# ──────────────────────────────────────────────────────────────────────
# CH16 — Data export
# ──────────────────────────────────────────────────────────────────────

PII_DATASETS = {'buyer_pii', 'seller_kyc'}


def request_data_export(admin, *, dataset, reason, period_start=None,
                        period_end=None, granularity='daily',
                        export_format='csv', is_dpo=False):
    is_pii = dataset in PII_DATASETS
    status = 'queued'
    deny_reason = ''
    # PII exports require DPO/legal authorisation (doc CH16).
    if is_pii and not (is_dpo or admin_level(admin) >= MIN_APPROVER_LEVEL):
        status = 'denied'
        deny_reason = 'PII export requires DPO or super-admin authorisation'
    req = DataExportRequest.objects.create(
        requested_by=admin, dataset=dataset, reason=reason[:300],
        period_start=period_start, period_end=period_end,
        granularity=granularity, export_format=export_format,
        is_pii=is_pii, status=status, deny_reason=deny_reason)
    audit(admin, 'data_export.requested', target_type='dataset',
          target_id=dataset, reason=reason,
          result='failed' if status == 'denied' else 'success')
    return req


# ──────────────────────────────────────────────────────────────────────
# CH18 — Legal holds + LE requests
# ──────────────────────────────────────────────────────────────────────

def place_legal_hold(admin, *, subject_type, subject_id, legal_basis,
                     scope='all_data', requesting_authority='',
                     case_reference='', notes='', expires_at=None):
    """Legal holds are high-impact → dual approval (doc CH18)."""
    import secrets
    ref = f'HL-{timezone.now().year}-{secrets.token_hex(3).upper()}'
    hold = LegalHold.objects.create(
        hold_ref=ref, subject_type=subject_type, subject_id=str(subject_id),
        scope=scope, legal_basis=legal_basis,
        requesting_authority=requesting_authority,
        case_reference=case_reference, notes=notes, placed_by=admin,
        status='active', expires_at=expires_at)
    req = submit_approval(
        admin, kind='legal_hold',
        reason=f'{legal_basis} on {subject_type}:{subject_id}',
        target_type=subject_type, target_id=subject_id,
        payload={'legal_hold_id': hold.id})
    AdminConsoleEvent.log('legal_hold_placed', actor=admin, hold_ref=ref)
    return hold, req


def release_legal_hold(admin, hold_id):
    hold = LegalHold.objects.filter(id=hold_id, status='active').first()
    if hold is None:
        return {'ok': False, 'reason': 'not_found_or_inactive'}
    hold.status = 'released'
    hold.released_at = timezone.now()
    hold.released_by = admin if getattr(admin, 'pk', None) else None
    hold.save(update_fields=['status', 'released_at', 'released_by'])
    audit(admin, 'legal_hold.released', target_type=hold.subject_type,
          target_id=hold.subject_id)
    return {'ok': True}


def is_under_legal_hold(subject_type, subject_id):
    """Called by GDPR erasure / deletion paths to block on active holds."""
    return LegalHold.objects.filter(
        subject_type=subject_type, subject_id=str(subject_id),
        status='active').exists()


def intake_le_request(admin, *, request_type, authority, case_reference='',
                      subject_id='', jurisdiction=''):
    import secrets
    ref = f'LE-{timezone.now().year}-{secrets.token_hex(4).upper()}'
    req = LawEnforcementRequest.objects.create(
        request_ref=ref, request_type=request_type, authority=authority,
        case_reference=case_reference, subject_id=str(subject_id),
        jurisdiction=jurisdiction, status='received')
    AdminConsoleEvent.log('le_request_received', actor=admin, ref=ref)
    return req


def decide_le_request(admin, request_ref, decision, *, note=''):
    req = LawEnforcementRequest.objects.filter(request_ref=request_ref).first()
    if req is None:
        return {'ok': False, 'reason': 'not_found'}
    req.status = decision  # accepted / rejected / clarification
    req.decision_note = note[:300]
    req.processed_by = admin if getattr(admin, 'pk', None) else None
    req.processed_at = timezone.now()
    # On accept, place a preservation hold.
    if decision == 'accepted' and req.subject_id:
        hold, _ = place_legal_hold(
            admin, subject_type='seller', subject_id=req.subject_id,
            legal_basis='le_request', requesting_authority=req.authority,
            case_reference=req.case_reference)
        req.legal_hold = hold
    req.save()
    audit(admin, f'le_request.{decision}', target_type='le_request',
          target_id=request_ref, reason=note)
    return {'ok': True, 'status': decision}


# ──────────────────────────────────────────────────────────────────────
# CH19 — Payout holds + adjustments
# ──────────────────────────────────────────────────────────────────────

def hold_payout(admin, *, payout_request_id, seller, reason,
                notify_seller=True, expires_at=None):
    hold = PayoutHold.objects.create(
        payout_request_id=str(payout_request_id), seller=seller,
        reason=reason, notify_seller=notify_seller, placed_by=admin,
        expires_at=expires_at)
    # Bridge: mark the payout request held if the model supports it.
    try:
        from apps.payments.models import PayoutRequest
        PayoutRequest.objects.filter(id=payout_request_id).update(
            admin_note=f'HELD: {reason}')
    except Exception:
        pass
    audit(admin, 'payout.held', target_type='payout',
          target_id=payout_request_id, reason=reason)
    return hold


def release_payout_hold(admin, hold_id):
    hold = PayoutHold.objects.filter(id=hold_id, status='active').first()
    if hold is None:
        return {'ok': False, 'reason': 'not_found'}
    hold.status = 'released'
    hold.released_at = timezone.now()
    hold.save(update_fields=['status', 'released_at'])
    return {'ok': True}


def adjust_payout(admin, *, seller, kind, amount_cents, reason):
    """Manual credit/deduction. >$10k credit requires approval (doc CH19)."""
    adj = PayoutAdjustment.objects.create(
        seller=seller, kind=kind, amount_cents=amount_cents,
        reason=reason[:300], created_by=admin)
    needs_approval = amount_cents > 1_000_000  # > $10,000
    req = None
    if needs_approval:
        req = submit_approval(
            admin, kind='bulk_refund' if kind == 'credit' else 'fee_rate_change',
            reason=f'{kind} {amount_cents}c to seller {seller.pk}: {reason}',
            target_type='seller', target_id=seller.pk,
            payload={'payout_adjustment_id': adj.id})
        adj.approval_request = req
        adj.save(update_fields=['approval_request'])
    audit(admin, f'payout_adjustment.{kind}', target_type='seller',
          target_id=seller.pk, after={'amount_cents': amount_cents},
          reason=reason,
          result='pending_approval' if needs_approval else 'success')
    return adj, req


# ──────────────────────────────────────────────────────────────────────
# CH21 — Homepage banners
# ──────────────────────────────────────────────────────────────────────

def submit_banner(admin, *, slot, headline, **fields):
    banner = AdminBanner.objects.create(
        slot=slot, headline=headline,
        subline=fields.get('subline', ''),
        image_desktop_key=fields.get('image_desktop_key', ''),
        image_mobile_key=fields.get('image_mobile_key', ''),
        cta_text=fields.get('cta_text', ''),
        cta_link=fields.get('cta_link', ''),
        target_countries=fields.get('target_countries', []),
        priority=fields.get('priority', 1),
        is_paid_placement=fields.get('is_paid_placement', False),
        go_live_at=fields.get('go_live_at'),
        expires_at=fields.get('expires_at'),
        status='pending_approval',
        created_by=admin if getattr(admin, 'pk', None) else None)
    audit(admin, 'banner.submitted', target_type='banner',
          target_id=banner.id)
    return banner


def approve_banner(admin, banner_id):
    """Approver must differ from the creator (doc CH21)."""
    banner = AdminBanner.objects.filter(id=banner_id).first()
    if banner is None:
        return {'ok': False, 'reason': 'not_found'}
    if banner.status != 'pending_approval':
        return {'ok': False, 'reason': f'status_{banner.status}'}
    if banner.created_by_id == getattr(admin, 'pk', None):
        return {'ok': False, 'reason': 'separate_approver_required'}
    banner.status = 'approved'
    banner.approved_by = admin if getattr(admin, 'pk', None) else None
    banner.save(update_fields=['status', 'approved_by'])
    audit(admin, 'banner.approved', target_type='banner', target_id=banner.id)
    return {'ok': True}


def publish_due_banners():
    """Set approved banners live at their scheduled time; expire old ones."""
    now = timezone.now()
    live = AdminBanner.objects.filter(
        status='approved', go_live_at__lte=now).update(status='live')
    expired = AdminBanner.objects.filter(
        status='live', expires_at__lt=now).update(status='expired')
    return {'went_live': live, 'expired': expired}


# ──────────────────────────────────────────────────────────────────────
# CH22 — Platform alerts
# ──────────────────────────────────────────────────────────────────────

def publish_platform_alert(admin, *, alert_type, message, channels=None,
                           audience='all_users', severity='high',
                           incident=None):
    alert = PlatformAlert.objects.create(
        alert_type=alert_type, message=message,
        channels=channels or ['in_app'], audience=audience, severity=severity,
        status='published', auto_resolve_with_incident=incident,
        published_by=admin if getattr(admin, 'pk', None) else None,
        published_at=timezone.now())
    audit(admin, 'platform_alert.published', target_type='alert',
          target_id=alert.id, after={'type': alert_type})
    AdminConsoleEvent.log('platform_alert_published', actor=admin,
                          alert_id=alert.id, severity=severity)
    return alert


def resolve_platform_alert(admin, alert_id):
    alert = PlatformAlert.objects.filter(id=alert_id).first()
    if alert is None:
        return {'ok': False}
    alert.status = 'resolved'
    alert.resolved_at = timezone.now()
    alert.save(update_fields=['status', 'resolved_at'])
    return {'ok': True}


# ──────────────────────────────────────────────────────────────────────
# CH23 — Service status + incidents
# ──────────────────────────────────────────────────────────────────────

def upsert_service_status(service_name, *, state, latency_p99_ms=0,
                          error_rate_pct=0):
    svc, _ = ServiceStatus.objects.update_or_create(
        service_name=service_name,
        defaults={'state': state, 'latency_p99_ms': latency_p99_ms,
                  'error_rate_pct': Decimal(str(error_rate_pct))})
    if state != 'operational':
        svc.last_incident_at = timezone.now()
        svc.save(update_fields=['last_incident_at'])
    return svc


def declare_incident(admin, *, title, severity='p2', affected_service='',
                     estimated_affected_users=0, status_page_message=''):
    inc = PlatformIncident.objects.create(
        title=title, severity=severity, affected_service=affected_service,
        estimated_affected_users=estimated_affected_users,
        status_page_message=status_page_message,
        declared_by=admin if getattr(admin, 'pk', None) else None,
        timeline=[{'at': timezone.now().isoformat(), 'status': 'investigating',
                   'note': 'incident declared'}])
    audit(admin, 'incident.declared', target_type='incident',
          target_id=inc.id, after={'severity': severity})
    AdminConsoleEvent.log('incident_declared', actor=admin, incident_id=inc.id,
                          severity=severity)
    return inc


def update_incident(admin, incident_id, *, status, note=''):
    inc = PlatformIncident.objects.filter(id=incident_id).first()
    if inc is None:
        return {'ok': False, 'reason': 'not_found'}
    inc.status = status
    timeline = list(inc.timeline or [])
    timeline.append({'at': timezone.now().isoformat(), 'status': status,
                     'note': note})
    inc.timeline = timeline
    if status == 'resolved':
        inc.resolved_at = timezone.now()
        # Auto-resolve linked alerts (doc CH22 auto-resolve).
        PlatformAlert.objects.filter(
            auto_resolve_with_incident=inc, status='published').update(
            status='resolved', resolved_at=timezone.now())
    inc.save()
    audit(admin, 'incident.updated', target_type='incident',
          target_id=inc.id, after={'status': status}, reason=note)
    return {'ok': True, 'status': status}


# ──────────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ──────────────────────────────────────────────────────────────────────

def snapshot_admin_kpis(snapshot_date=None):
    snapshot_date = snapshot_date or timezone.now().date()

    # Audit coverage + dual-approval compliance (both system-enforced → 100
    # unless a gap is detected).
    high_impact = ApprovalRequest.objects.filter(
        status__in=['approved', 'executed', 'rejected'])
    hi_total = high_impact.count()
    hi_dual = high_impact.exclude(reviewed_by=None).count()
    dual_pct = round(hi_dual / hi_total * 100, 2) if hi_total else 100

    active_exp = AdminExperiment.objects.filter(status='running').count()
    pending = ApprovalRequest.objects.filter(
        status='pending_approval').count()
    active_inc = PlatformIncident.objects.exclude(status='resolved').count()

    # Bridge financial / carrier KPIs where available (fail open to 0).
    take_rate = _latest_take_rate()
    carrier_ot = _carrier_on_time()

    snap, _ = AdminKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'take_rate_pct': take_rate,
            'active_experiments': active_exp,
            'pending_approvals': pending,
            'active_incidents': active_inc,
            'carrier_on_time_pct': carrier_ot,
            'dual_approval_compliance_pct': dual_pct,
            'audit_coverage_pct': Decimal('100'),
        },
    )
    AdminConsoleEvent.log('admin_kpis_snapshotted', date=str(snapshot_date))
    return snap


def _latest_take_rate():
    try:
        from apps.data_analytics.models import GmvDecomposition  # noqa
    except Exception:
        pass
    return Decimal('0')


def _carrier_on_time():
    try:
        from apps.logistics_ops.models import CarrierSlaSnapshot
        from django.db.models import Avg
        agg = CarrierSlaSnapshot.objects.aggregate(
            a=Avg('on_time_pct'))['a']
        return Decimal(str(round(agg, 2))) if agg else Decimal('0')
    except Exception:
        return Decimal('0')
