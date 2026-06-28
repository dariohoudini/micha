from django.urls import path

from .views import (
    IpRightsHolderView, MyTrustScoreView, TsKpiView,
    age_gate_check, appeal_decide, appeal_file, ato_open,
    ato_resolve, ban_evasion_record, blacklist_add,
    blacklist_check, buyer_fraud_ring_declare,
    coordinated_buying_detect, counterfeit_case_resolve,
    counterfeit_signal_record, csam_check_hash, csam_quarantine,
    dmca_counter_file, dmca_file, edd_decide, edd_open,
    edd_submit_docs, export_control_check, hate_speech_detect,
    hate_speech_enforce, impersonation_check, ip_complaint_decide,
    ip_complaint_file, ip_complaint_respond, le_request_receive,
    le_request_respond, legal_hold_release, legal_hold_start,
    price_gouging_detect, prohibited_scan_image,
    prohibited_scan_text, recall_initiate, recall_notify,
    refund_farming_open, review_fraud_ring_declare,
    review_signal_record, serial_disputer_signal, user_block,
    user_report_file,
)


urlpatterns = [
    # CH2 — prohibited
    path('prohibited/scan-text/',     prohibited_scan_text, name='ts-prohibited-text'),
    path('prohibited/scan-image/',    prohibited_scan_image, name='ts-prohibited-image'),
    # CH3 — counterfeit
    path('counterfeit/signal/',       counterfeit_signal_record, name='ts-cf-signal'),
    path('counterfeit/resolve/',      counterfeit_case_resolve, name='ts-cf-resolve'),
    # CH4 — CSAM
    path('csam/check-hash/',          csam_check_hash, name='ts-csam-check'),
    path('csam/quarantine/',          csam_quarantine, name='ts-csam-quarantine'),
    # CH5 — hate speech
    path('hate-speech/detect/',       hate_speech_detect, name='ts-hate-detect'),
    path('hate-speech/enforce/',      hate_speech_enforce, name='ts-hate-enforce'),
    # CH6 — IP complaints
    path('ip/rights-holders/',        IpRightsHolderView.as_view(), name='ts-ip-rh'),
    path('ip/complaints/file/',       ip_complaint_file, name='ts-ip-file'),
    path('ip/complaints/respond/',    ip_complaint_respond, name='ts-ip-respond'),
    path('ip/complaints/decide/',     ip_complaint_decide, name='ts-ip-decide'),
    # CH7 — DMCA
    path('dmca/notices/',             dmca_file, name='ts-dmca-file'),
    path('dmca/counter-notices/',     dmca_counter_file, name='ts-dmca-counter'),
    # CH8 — price gouging
    path('price-gouging/detect/',     price_gouging_detect, name='ts-gouging'),
    # CH9 — impersonation + ban evasion
    path('impersonation/check/',      impersonation_check, name='ts-imp-check'),
    path('ban-evasion/record/',       ban_evasion_record, name='ts-ban-evasion'),
    # CH10 — coordinated buying
    path('coordinated-buying/detect/', coordinated_buying_detect, name='ts-coord-buy'),
    # CH11 — age gates
    path('age-gate/check/',           age_gate_check, name='ts-age-gate'),
    # CH12 — block + report
    path('blocks/',                   user_block, name='ts-block'),
    path('reports/',                  user_report_file, name='ts-report'),
    # CH13 — blacklist
    path('blacklist/add/',            blacklist_add, name='ts-bl-add'),
    path('blacklist/check/',          blacklist_check, name='ts-bl-check'),
    # CH14 — review fraud
    path('review-fraud/signal/',      review_signal_record, name='ts-rev-signal'),
    path('review-fraud/ring/',        review_fraud_ring_declare, name='ts-rev-ring'),
    # CH15 — ATO
    path('ato/open/',                 ato_open, name='ts-ato-open'),
    path('ato/resolve/',              ato_resolve, name='ts-ato-resolve'),
    # CH16 — EDD
    path('edd/open/',                 edd_open, name='ts-edd-open'),
    path('edd/submit-docs/',          edd_submit_docs, name='ts-edd-docs'),
    path('edd/decide/',               edd_decide, name='ts-edd-decide'),
    # CH17 — serial disputer + refund farmer
    path('serial-disputer/signal/',   serial_disputer_signal, name='ts-serial'),
    path('refund-farming/open/',      refund_farming_open, name='ts-rf-open'),
    # CH18 — buyer fraud rings
    path('buyer-fraud-ring/declare/', buyer_fraud_ring_declare, name='ts-bfr'),
    # CH19 — recalls
    path('recalls/initiate/',         recall_initiate, name='ts-recall'),
    path('recalls/notify/',           recall_notify, name='ts-recall-notify'),
    # CH20 — export control
    path('export-control/check/',     export_control_check, name='ts-export'),
    # CH21 — buyer trust score
    path('trust-score/me/',           MyTrustScoreView.as_view(), name='ts-trust-me'),
    # CH22 — appeals
    path('appeals/',                  appeal_file, name='ts-appeal'),
    path('appeals/decide/',           appeal_decide, name='ts-appeal-decide'),
    # CH23 — LE requests
    path('le-requests/',              le_request_receive, name='ts-le-receive'),
    path('le-requests/respond/',      le_request_respond, name='ts-le-respond'),
    path('legal-holds/',              legal_hold_start, name='ts-hold-start'),
    path('legal-holds/release/',      legal_hold_release, name='ts-hold-release'),
    # CH24 — KPI
    path('admin/kpi/',                TsKpiView.as_view(), name='ts-kpi'),
]
