"""
Seller onboarding — Django signal hooks
========================================

The application state machine fires `application_status_changed`
after every transition. Receivers below translate the FSM moves
into side-effects defined by the doc:

  kyc_approved   → generate + send the personalised agreement (CH4.1)
  agreement_signed → create the annual-fee invoice (CH5.2)
  fee_paid       → final seller activation transaction (CH5.3)
                   + welcome-package application (CH9.1)

Receivers are intentionally minimal — they call into services.py so
the same logic is reusable from Celery tasks (re-sign campaign,
admin override).
"""
from django.dispatch import Signal, receiver

application_status_changed = Signal()


@receiver(application_status_changed)
def _on_status_changed(sender, application, old_status, new_status, actor=None, **kwargs):
    # Lazy import to dodge AppRegistryNotReady at boot.
    from . import services

    if new_status == 'kyc_approved':
        try: services.generate_agreement_for(application)
        except Exception: pass

    if new_status == 'agreement_signed':
        try: services.issue_annual_fee_invoice(application)
        except Exception: pass

    if new_status == 'fee_paid':
        try: services.activate_seller(application)
        except Exception: pass
