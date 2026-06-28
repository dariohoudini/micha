from django.urls import path

from .views import (
    ActivePromotionsView, AdminAbuseSignalsView,
    EmailCampaignView, FlashSaleApplicationView, FlashSaleStockView,
    MarketingKpiView, PushCampaignView, SegmentView,
    SellerAdCampaignView, SellerBundleView, SellerFreeGiftView,
    SellerVolumeDiscountView, SmsCampaignView,
    ad_auction, ad_click, compute_lift_view,
    compute_volume_discount, coupon_collect, coupon_redeem,
    detect_bundles_for_cart, detect_free_gifts,
    materialise_segment_view, pixel_emit, play_game,
    reserve_flash_stock, resolve_cart_promotions, share_scratch,
    sms_optin, sms_optout,
)


urlpatterns = [
    # CH1 — public list
    path('promotions/active/', ActivePromotionsView.as_view(), name='me-active'),
    # CH2/3 — resolve cart
    path('promotions/resolve/', resolve_cart_promotions, name='me-resolve'),
    # CH9 — coupon collect/redeem
    path('coupons/collect/', coupon_collect, name='me-coupon-collect'),
    path('coupons/redeem/', coupon_redeem, name='me-coupon-redeem'),
    # CH4 — flash sale applications
    path('flash-sales/applications/', FlashSaleApplicationView.as_view(),
         name='me-flash-applications'),
    # CH5 — flash sale stock
    path('flash-sales/<str:event_slug>/stock/', FlashSaleStockView.as_view(),
         name='me-flash-stock'),
    path('flash-sales/reserve/', reserve_flash_stock, name='me-flash-reserve'),
    # CH6 — bundles
    path('bundles/', SellerBundleView.as_view(), name='me-bundles'),
    path('bundles/detect/', detect_bundles_for_cart, name='me-bundles-detect'),
    # CH7 — volume discount
    path('volume-discounts/', SellerVolumeDiscountView.as_view(),
         name='me-volume-discounts'),
    path('volume-discounts/compute/', compute_volume_discount,
         name='me-volume-compute'),
    # CH8 — free gift
    path('free-gifts/', SellerFreeGiftView.as_view(), name='me-free-gifts'),
    path('free-gifts/detect/', detect_free_gifts, name='me-gifts-detect'),
    # CH10 — games
    path('games/<uuid:game_id>/play/', play_game, name='me-game-play'),
    path('games/<uuid:game_id>/share-scratch/', share_scratch,
         name='me-game-share'),
    # CH14 — ad auction
    path('ads/auction/', ad_auction, name='me-ad-auction'),
    path('ads/click/', ad_click, name='me-ad-click'),
    path('ads/campaigns/', SellerAdCampaignView.as_view(), name='me-ad-campaigns'),
    # CH16 — pixel
    path('pixel/emit/', pixel_emit, name='me-pixel-emit'),
    # CH17 — segments + email
    path('segments/', SegmentView.as_view(), name='me-segments'),
    path('segments/<slug:slug>/materialise/', materialise_segment_view,
         name='me-segment-materialise'),
    path('email-campaigns/', EmailCampaignView.as_view(),
         name='me-email-campaigns'),
    # CH18 — SMS
    path('sms/opt-in/', sms_optin, name='me-sms-optin'),
    path('sms/opt-out/', sms_optout, name='me-sms-optout'),
    path('sms/campaigns/', SmsCampaignView.as_view(), name='me-sms-campaigns'),
    # CH19 — push
    path('push-campaigns/', PushCampaignView.as_view(), name='me-push-campaigns'),
    # CH22 — lift
    path('admin/lift/', compute_lift_view, name='me-lift'),
    # CH23 — abuse
    path('admin/abuse-signals/', AdminAbuseSignalsView.as_view(),
         name='me-abuse-signals'),
    # CH24 — KPI
    path('admin/kpi/', MarketingKpiView.as_view(), name='me-kpi'),
]
