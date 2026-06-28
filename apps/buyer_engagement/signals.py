"""
Buyer engagement signal wiring. Most cross-app effects (first-purchase
detection on order creation, dormancy recompute on session start) are
plumbed via standard Django signals so the wider codebase doesn't
need to know about this app.
"""
from django.dispatch import Signal

# Fires when a new buyer completes their first purchase. Receivers
# release rewards: referral bonus, welcome incentive marked used,
# welcome coins.
first_purchase_completed = Signal()

# Fires when a recovery sequence converts (purchase made while a
# sequence was active). Receivers stop the sequence and attribute the
# conversion.
recovery_converted = Signal()

# Fires when premium membership state changes.
membership_state_changed = Signal()
