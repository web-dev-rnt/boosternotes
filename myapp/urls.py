from django.contrib import admin
from django.urls import path, re_path
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from myapp import views
from myapp import razorpay_views
from myapp.backup_views import backup_panel
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.user_login, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('signup/', views.signup, name='signup'),
    path('logout/', auth_views.LogoutView.as_view(next_page=reverse_lazy('home')), name='logout'),

    # User profile
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/purchases/', views.my_purchases, name='my_purchases'),

    # Cart & Checkout
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<str:item_key>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/apply-coupon/', views.apply_cart_coupon, name='apply_cart_coupon'),
    path('cart/remove-coupon/', views.remove_cart_coupon, name='remove_cart_coupon'),
    path('checkout/', views.checkout, name='checkout'),

    # Razorpay payment
    path('payment/create-order/', razorpay_views.razorpay_create_order, name='razorpay_create_order'),
    path('payment/verify/', razorpay_views.razorpay_verify_payment, name='razorpay_verify_payment'),
    path('payment/cancel/', razorpay_views.razorpay_cancel_order, name='razorpay_cancel_order'),
    path('order/success/<uuid:order_id>/', razorpay_views.order_success, name='order_success'),

    # Admin: Orders
    path('admin-orders/', razorpay_views.orders_dashboard, name='orders_dashboard'),
    path('admin-orders/<uuid:order_id>/', razorpay_views.order_detail, name='order_detail'),
    path('admin-orders/<uuid:order_id>/status/', razorpay_views.order_update_status, name='order_update_status'),
    path('admin-orders/<uuid:order_id>/delete/', razorpay_views.order_delete, name='order_delete'),

    # User management
    path('users/add/', views.add_user, name='add_user'),
    path('users/edit/<int:user_id>/', views.edit_user, name='edit_user'),
    path('users/delete/<int:user_id>/', views.delete_user, name='delete_user'),

    # Notifications
    path('notifications/', views.notifications_section, name='notifications_section'),
    path('notifications/<int:notification_id>/delete/', views.delete_notification, name='delete_notification'),
    path('notifications/api/', views.notifications_api, name='notifications_api'),

    # Coupons
    path('coupon_list', views.coupon_list, name='coupon_list'),
    path('delete/<int:pk>/', views.coupon_delete, name='coupon_delete'),
    path('toggle/<int:pk>/', views.coupon_toggle_active, name='coupon_toggle_active'),

    # Category - admin
    path('category_list', views.category_list, name='category_list'),
    path('category/edit/<int:pk>/', views.category_edit, name='category_edit'),
    path('category/delete/<int:pk>/', views.category_delete, name='category_delete'),
    path('category/toggle/<int:pk>/', views.category_toggle_active, name='category_toggle_active'),

    # Category - public
    path('categories/', views.all_categories, name='all_categories'),
    path('category/<int:category_id>/courses/', views.category_courses_view, name='category_courses_view'),

    # Navbar / Banner / Stats / About / Footer
    path('navbar/', views.navbar_custom, name='navbar_custom'),
    path('banner/', views.banner_custom, name='banner_custom'),
    path('stats/', views.stats_custom, name='stats_custom'),
    path('stats/edit/<int:pk>/', views.stats_edit, name='stats_edit'),
    path('stats/delete/<int:pk>/', views.stats_delete, name='stats_delete'),
    path('about/', views.about_custom, name='about_custom'),
    path('footer/', views.footer_custom, name='footer_custom'),

    # E-Library
    path('elibrary/', views.elibrary_dashboard, name='elibrary_dashboard'),
    path('elibrary/add/', views.elibrary_add, name='elibrary_add'),
    path('elibrary/edit/<uuid:pk>/', views.elibrary_edit, name='elibrary_edit'),
    path('elibrary/delete/<uuid:id>/', views.elibrary_delete, name='elibrary_delete'),
    path('elibrary/<uuid:pk>/upload-pdf/', views.elibrary_upload_pdf, name='elibrary_upload_pdf'),
    path('elibrary/pdf/delete/<uuid:pk>/', views.elibrary_pdf_delete, name='elibrary_pdf_delete'),
    path('elibrary/pdf/replace/<uuid:pk>/', views.elibrary_pdf_replace, name='elibrary_pdf_replace'),
    path('elibrary/<uuid:pk>/reorder-pdfs/', views.elibrary_pdf_reorder, name='elibrary_pdf_reorder'),

    # PDF proxy — streams Dropbox file through Django (no client-side Dropbox auth)
    path('elibrary/pdf/<uuid:pdf_id>/preview/', views.elibrary_pdf_preview, name='elibrary_pdf_preview'),

    # Hard Books - admin
    path('hard-books/', views.hard_books_list, name='hard_books_list'),
    path('hard-books/add/', views.hard_book_add, name='hard_book_add'),
    path('hard-books/edit/<uuid:pk>/', views.hard_book_edit, name='hard_book_edit'),
    path('hard-books/delete/<uuid:pk>/', views.hard_book_delete, name='hard_book_delete'),
    path('hard-books/image-delete/<uuid:pk>/', views.hard_book_image_delete, name='hard_book_image_delete'),

    # Hard Books - public
    path('books/', views.hard_books_public, name='hard_books_public'),

    path('search/', views.search, name='search'),
    path('apply-coupon/', views.apply_coupon, name='apply_coupon'),

    path('elibrary/<uuid:pk>/', views.elibrary_detail, name='elibrary_detail'),
    path('hard-books/<uuid:pk>/', views.hard_book_detail, name='hard_book_detail'),

    # DB Backup & Restore Panel
    path('db-backup/', backup_panel, name='backup_panel'),

    # ── Catch-all 404 ─────────────────────────────────────────────────────────────────────────────────
    re_path(r'^(?!media/|static/).*$', views.custom_404_view, name='custom_404'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
