from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q, F, Prefetch, Sum
from django.http import (
    JsonResponse, HttpResponseRedirect,
    StreamingHttpResponse, HttpResponse, Http404,
)
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.timesince import timesince
from django.core.files.storage import default_storage
import uuid

from .models import *
from .forms import *

from .dropbox_utils import DropboxManager, DropboxPaths
from .pdf_utils import compress_pdf, human_size
import os
from django.core.files.base import ContentFile


# ── Cache helpers ─────────────────────────────────────────────────────────────────────
def _get_navbar():
    navbar = cache.get('navbar_setting')
    if navbar is None:
        navbar = NavbarSetting.objects.first()
        cache.set('navbar_setting', navbar, 3600)  # 1 hour
    return navbar

def _get_footer():
    footer = cache.get('footer_setting')
    if footer is None:
        footer = FooterSetting.objects.first()
        cache.set('footer_setting', footer, 3600)
    return footer

def _get_about():
    about = cache.get('about_setting')
    if about is None:
        about = AboutSetting.objects.first()
        cache.set('about_setting', about, 3600)
    return about


# ── Notifications API ────────────────────────────────────────────────────────────
def notifications_api(request):
    notifs = Notification.objects.order_by('-sent_at')[:10]
    data = [{'id': n.id, 'title': n.title, 'message': n.message, 'link': n.link or '', 'time': timesince(n.sent_at) + ' ago'} for n in notifs]
    return JsonResponse({'notifications': data, 'count': len(data)})


# ── Edit Profile ─────────────────────────────────────────────────────────────────
@login_required
def edit_profile(request):
    if request.method == 'POST':
        username         = request.POST.get('username', '').strip()
        email            = request.POST.get('email', '').strip()
        first_name       = request.POST.get('first_name', '').strip()
        last_name        = request.POST.get('last_name', '').strip()
        password         = request.POST.get('password', '').strip()
        password_confirm = request.POST.get('password_confirm', '').strip()
        user = request.user
        if username and username != user.username:
            if User.objects.filter(username=username).exclude(pk=user.pk).exists():
                messages.error(request, 'That username is already taken.')
                return redirect('edit_profile')
        if username:
            user.username = username
        user.email      = email
        user.first_name = first_name
        user.last_name  = last_name
        if password:
            if password != password_confirm:
                messages.error(request, 'Passwords do not match.')
                return redirect('edit_profile')
            user.set_password(password)
            user.save()
            update_session_auth_hash(request, user)
        else:
            user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('edit_profile')
    return render(request, 'edit_profile.html')


# ── My Purchases ─────────────────────────────────────────────────────────────────
@login_required
def my_purchases(request):
    from .models import Order
    orders = Order.objects.filter(user=request.user, is_paid=True).prefetch_related('items').order_by('-paid_at')
    return render(request, 'my_purchases.html', {'orders': orders})


# ── Cart helpers ─────────────────────────────────────────────────────────────────
def _get_cart(request):
    return request.session.get('cart', {})

def _save_cart(request, cart):
    request.session['cart'] = cart
    request.session.modified = True

def _build_cart_items(cart):
    """Batch-fetch cart items in 2 queries instead of 1 query per item."""
    pdf_ids  = [v['id'] for v in cart.values() if v.get('type') == 'pdf']
    book_ids = [v['id'] for v in cart.values() if v.get('type') == 'book']

    pdf_map  = {str(o.id): o for o in ELibraryModel.objects.filter(id__in=pdf_ids).select_related('category')}
    book_map = {str(o.id): o for o in HardBook.objects.filter(id__in=book_ids).prefetch_related('images')}

    items = []
    for key, data in cart.items():
        item_type = data.get('type')
        item_id   = data.get('id')
        try:
            if item_type == 'pdf' and item_id in pdf_map:
                obj   = pdf_map[item_id]
                thumb = obj.thumbnail.url if obj.thumbnail else None
                items.append({'id': key, 'item_type': 'PDF Course', 'name': obj.name, 'thumbnail': thumb, 'category': obj.category.name if obj.category else '', 'price': obj.current_price, 'original_price': obj.original_price})
            elif item_type == 'book' and item_id in book_map:
                obj       = book_map[item_id]
                first_img = next(iter(obj.images.all()), None)
                thumb     = first_img.image.url if first_img and first_img.image else None
                items.append({'id': key, 'item_type': 'Physical Book', 'name': obj.title, 'thumbnail': thumb, 'category': '', 'price': obj.price, 'original_price': obj.original_price})
        except Exception:
            pass
    return items


# ── Add to Cart ─────────────────────────────────────────────────────────────────
@require_POST
def add_to_cart(request):
    item_id     = request.POST.get('item_id', '').strip()
    item_type   = request.POST.get('item_type', '').strip()
    redirect_to = request.POST.get('redirect_to', '').strip()

    redirect_back = request.META.get('HTTP_REFERER', '/')
    if not item_id or item_type not in ('pdf', 'book'):
        messages.error(request, 'Invalid item.')
        return redirect(redirect_back)

    cart = _get_cart(request)
    key  = f"{item_type}_{item_id}"
    if key not in cart:
        cart[key] = {'id': item_id, 'type': item_type}
        _save_cart(request, cart)
        messages.success(request, '\u2705 Added to cart!')
    else:
        messages.info(request, 'Item is already in your cart.')

    if redirect_to == 'checkout':
        return redirect('checkout')
    return redirect(redirect_back)


# ── Remove from Cart ────────────────────────────────────────────────────────────
@require_POST
def remove_from_cart(request, item_key):
    cart = _get_cart(request)
    cart.pop(item_key, None)
    _save_cart(request, cart)
    messages.success(request, 'Item removed from cart.')
    return redirect('cart')


# ── Cart Page ─────────────────────────────────────────────────────────────────
def cart_view(request):
    cart       = _get_cart(request)
    cart_items = _build_cart_items(cart)
    subtotal   = sum(item['price'] for item in cart_items)
    applied    = None
    coupon_id  = request.session.get('applied_coupon_id')
    if coupon_id:
        try:
            applied = Coupon.objects.get(id=coupon_id, is_active=True)
        except Coupon.DoesNotExist:
            request.session.pop('applied_coupon_id', None)
    discount    = applied.amount if applied else 0
    grand_total = max(0, subtotal - discount)
    return render(request, 'cart.html', {'cart_items': cart_items, 'subtotal': subtotal, 'applied_coupon': applied, 'grand_total': grand_total})


# ── Apply Coupon (cart page) ──────────────────────────────────────────────────────
@require_POST
def apply_cart_coupon(request):
    code = request.POST.get('code', '').strip().upper()
    if not code:
        messages.error(request, 'Enter a coupon code.')
        return redirect('cart')
    try:
        coupon = Coupon.objects.get(code__iexact=code, is_active=True)
    except Coupon.DoesNotExist:
        messages.error(request, '\u274c Invalid or expired coupon.')
        return redirect('cart')
    if coupon.is_expired:
        messages.error(request, '\u274c Coupon has expired.')
        return redirect('cart')
    if coupon.remaining_uses <= 0:
        messages.error(request, '\u274c Coupon usage limit reached.')
        return redirect('cart')
    request.session['applied_coupon_id']     = coupon.id
    request.session['applied_coupon_code']   = coupon.code
    request.session['applied_coupon_amount'] = str(coupon.amount)
    messages.success(request, f'\u2705 Coupon \'{coupon.code}\' applied! Save \u20b9{coupon.amount}')
    return redirect('cart')


# ── Remove Cart Coupon ────────────────────────────────────────────────────────────
@require_POST
def remove_cart_coupon(request):
    for key in ('applied_coupon_id', 'applied_coupon_code', 'applied_coupon_amount'):
        request.session.pop(key, None)
    messages.info(request, 'Coupon removed.')
    return redirect('cart')


# ── Checkout ─────────────────────────────────────────────────────────────────
@login_required
def checkout(request):
    cart = _get_cart(request)
    if not cart:
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')
    cart_items = _build_cart_items(cart)
    subtotal   = sum(item['price'] for item in cart_items)
    applied    = None
    coupon_id  = request.session.get('applied_coupon_id')
    if coupon_id:
        try:
            applied = Coupon.objects.get(id=coupon_id, is_active=True)
        except Coupon.DoesNotExist:
            pass
    discount    = applied.amount if applied else 0
    grand_total = max(0, subtotal - discount)
    return render(request, 'checkout.html', {'cart_items': cart_items, 'subtotal': subtotal, 'applied_coupon': applied, 'grand_total': grand_total})


# ── Place Order (legacy fallback) ──────────────────────────────────────────────
@login_required
@require_POST
def place_order(request):
    cart = _get_cart(request)
    if not cart:
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')
    request.session.pop('cart', None)
    for key in ('applied_coupon_id', 'applied_coupon_code', 'applied_coupon_amount'):
        request.session.pop(key, None)
    order_ref = str(uuid.uuid4())[:8].upper()
    return render(request, 'order_success.html', {'order_ref': order_ref})


# ── All Categories (public) ─────────────────────────────────────────────────────────
def all_categories(request):
    categories = Category.objects.filter(is_active=True).annotate(pdf_count=Count('elibrary_courses')).order_by('name')
    total_categories = categories.count()
    from django.db.models import IntegerField, Value
    from django.db.models.functions import Coalesce
    total_courses = (ELibraryModel.objects.filter(is_active=True).count() + HardBook.objects.filter(is_active=True).count())
    return render(request, 'all_categories.html', {'categories': categories, 'total_categories': total_categories, 'total_courses': total_courses, 'navbar': _get_navbar(), 'footer': _get_footer(), 'cart_count': len(request.session.get('cart', {}))})


# ── Category Courses (public) ───────────────────────────────────────────────────────
def category_courses_view(request, category_id):
    category = get_object_or_404(Category, id=category_id, is_active=True)
    elibrary_courses = ELibraryModel.objects.filter(category=category, is_active=True).select_related('category').only('id', 'name', 'current_price', 'original_price', 'thumbnail', 'category_id')
    hardcopy_courses = HardBook.objects.filter(is_active=True).prefetch_related(Prefetch('images', queryset=HardBookImage.objects.order_by('uploaded_at'))) if hasattr(HardBook, 'category') else []
    total_courses = elibrary_courses.count()
    return render(request, 'category_courses.html', {'category': category, 'elibrary_courses': elibrary_courses, 'hardcopy_courses': hardcopy_courses, 'total_courses': total_courses, 'navbar': _get_navbar(), 'footer': _get_footer(), 'cart_count': len(request.session.get('cart', {}))})


# ── Search ───────────────────────────────────────────────────────────────────────
def search(request):
    query = request.GET.get('q', '').strip()
    if query:
        category_results = Category.objects.filter(name__icontains=query, is_active=True)
        elibrary_results = ELibraryModel.objects.filter(name__icontains=query, is_active=True).select_related('category').only('id', 'name', 'current_price', 'thumbnail', 'category_id')
        hardbook_results = HardBook.objects.filter(title__icontains=query, is_active=True).prefetch_related(Prefetch('images', queryset=HardBookImage.objects.order_by('uploaded_at')[:1]))
    else:
        category_results = Category.objects.none()
        elibrary_results = ELibraryModel.objects.none()
        hardbook_results = HardBook.objects.none()

    total_results = (category_results.count() + elibrary_results.count() + hardbook_results.count())
    active_coupons = Coupon.objects.filter(is_active=True, expiry_date__gte=timezone.now().date(), usage_limit__gt=F('times_used')).order_by('-created_at')[:6]

    return render(request, 'search_results.html', {'navbar': _get_navbar(), 'footer': _get_footer(), 'search_query': query, 'category_results': category_results, 'elibrary_results': elibrary_results, 'hardbook_results': hardbook_results, 'total_results': total_results, 'active_coupons': active_coupons})


# ── Hard Books (admin) ───────────────────────────────────────────────────────────────────
@login_required
def hard_books_list(request):
    books = HardBook.objects.prefetch_related('images').all()
    return render(request, 'hard_books_list.html', {'books': books})


# ── Hard Books Public Dashboard ──────────────────────────────────────────────────────
def hard_books_public(request):
    books = HardBook.objects.filter(is_active=True).prefetch_related(
        Prefetch('images', queryset=HardBookImage.objects.order_by('uploaded_at'))
    ).order_by('-created_at')
    return render(request, 'hard_books_public.html', {
        'books': books,
        'navbar': _get_navbar(),
        'footer': _get_footer(),
        'cart_count': len(request.session.get('cart', {})),
    })


@login_required
def hard_book_add(request):
    if request.method == 'POST':
        form  = HardBookForm(request.POST)
        files = request.FILES.getlist('images')
        if form.is_valid():
            book = form.save()
            for i, file_obj in enumerate(files[:5], start=1):
                result = DropboxManager.upload_file(
                    file_obj=file_obj,
                    file_name=f"{book.title.replace(' ', '_')}_{i}_{file_obj.name}",
                    folder_path=DropboxPaths.hardbooks_images(),
                )
                if result['success']:
                    HardBookImage.objects.create(book=book, image=file_obj, dropbox_path=result['dropbox_path'])
                else:
                    messages.error(request, f"Image {i} upload failed: {result['error']}")
            messages.success(request, 'Hard book added successfully!')
            return redirect('hard_books_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = HardBookForm()
    return render(request, 'hard_book_form.html', {'form': form})


@login_required
def hard_book_edit(request, pk):
    book = get_object_or_404(HardBook, pk=pk)
    if request.method == 'POST':
        form  = HardBookForm(request.POST, instance=book)
        files = request.FILES.getlist('images')
        if form.is_valid():
            book            = form.save()
            available_slots = max(0, 5 - book.images.count())
            for i, file_obj in enumerate(files[:available_slots], start=1):
                result = DropboxManager.upload_file(
                    file_obj=file_obj,
                    file_name=f"{book.title.replace(' ', '_')}_{i}_{file_obj.name}",
                    folder_path=DropboxPaths.hardbooks_images(),
                )
                if result['success']:
                    HardBookImage.objects.create(book=book, image=file_obj, dropbox_path=result['dropbox_path'])
                else:
                    messages.error(request, f"Image upload failed: {result['error']}")
            messages.success(request, 'Hard book updated successfully!')
            return redirect('hard_books_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = HardBookForm(instance=book)
    return render(request, 'hard_book_form.html', {'form': form, 'book': book})


@login_required
def hard_book_delete(request, pk):
    book = get_object_or_404(HardBook, pk=pk)
    if request.method == 'POST':
        book.delete()
        messages.success(request, 'Hard book deleted successfully!')
    return redirect('hard_books_list')


@login_required
def hard_book_image_delete(request, pk):
    img = get_object_or_404(HardBookImage, pk=pk)
    if request.method == 'POST':
        DropboxManager.delete_file(img.dropbox_path)
        img.delete()
        messages.success(request, 'Image deleted successfully!')
    return redirect('hard_books_list')


# ── E-Library (admin) ────────────────────────────────────────────────────────────
@login_required
def elibrary_dashboard(request):
    courses     = ELibraryModel.objects.select_related('category').all()
    category_id = request.GET.get('category')
    if category_id:
        courses = courses.filter(category_id=category_id)
    categories = Category.objects.filter(is_active=True).only('id', 'name')
    return render(request, 'elibrary/dashboard.html', {'courses': courses, 'categories': categories})


@login_required
def elibrary_add(request):
    if request.method == 'POST':
        form = ELibraryForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save(commit=False)
            if 'thumbnail' in request.FILES:
                thumb_file = request.FILES['thumbnail']
                result = DropboxManager.upload_file(
                    file_obj=thumb_file,
                    file_name=thumb_file.name,
                    folder_path=DropboxPaths.elibrary_images(course.name),
                )
                if result['success']:
                    course.dropbox_thumbnail_path = result['dropbox_path']
            course.save()
            messages.success(request, 'E-Library course added successfully!')
            return redirect('elibrary_dashboard')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ELibraryForm()
    return render(request, 'elibrary/add.html', {'form': form})


@login_required
def elibrary_edit(request, pk):
    course = get_object_or_404(ELibraryModel, pk=pk)
    if request.method == 'POST':
        form = ELibraryForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            course = form.save(commit=False)
            if 'thumbnail' in request.FILES:
                thumb_file = request.FILES['thumbnail']
                result = DropboxManager.upload_file(
                    file_obj=thumb_file,
                    file_name=thumb_file.name,
                    folder_path=DropboxPaths.elibrary_images(course.name),
                )
                if result['success']:
                    course.dropbox_thumbnail_path = result['dropbox_path']
            course.save()
            messages.success(request, 'E-Library course updated successfully!')
            return redirect('elibrary_dashboard')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ELibraryForm(instance=course)
    return render(request, 'elibrary/edit.html', {'form': form, 'course': course})


@login_required
def elibrary_delete(request, id):
    course = get_object_or_404(ELibraryModel, id=id)
    if request.method == 'POST':
        course.delete()
        messages.success(request, 'Course deleted successfully!')
    return redirect('elibrary_dashboard')


from django.conf import settings


@login_required
def elibrary_upload_pdf(request, pk):
    """
    Upload a PDF for an eLibrary course.

    The file is compressed (losslessly) before being sent to Dropbox.
    Storage path: BoosterNotes/eLibrary/<course name>/PDFs/<filename>
    """
    course = get_object_or_404(ELibraryModel, pk=pk)
    if request.method == 'POST':
        form = ELibraryPDFForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['pdf_file']
            original_name = uploaded_file.name

            compressed_bytes, orig_size, comp_size, method = compress_pdf(uploaded_file)
            saved_pct = round((1 - comp_size / orig_size) * 100) if orig_size else 0

            compressed_file      = ContentFile(compressed_bytes, name=original_name)
            compressed_file.size = comp_size

            result = DropboxManager.upload_file(
                compressed_file,
                original_name,
                folder_path=DropboxPaths.elibrary_pdfs(course.name),
            )

            if result['success']:
                pdf              = form.save(commit=False)
                pdf.course       = course
                pdf.dropbox_path = result['dropbox_path']
                pdf.save()

                if method == 'passthrough' or saved_pct <= 0:
                    messages.success(request, f'\u2705 PDF uploaded! ({human_size(orig_size)} \u2014 already optimal)')
                else:
                    messages.success(
                        request,
                        f'\u2705 PDF uploaded & compressed via {method}! '
                        f'{human_size(orig_size)} \u2192 {human_size(comp_size)} (saved {saved_pct}\u00a0%)'
                    )
                return JsonResponse({'success': True, 'redirect': f"/elibrary/upload/{course.pk}/"})
            else:
                messages.error(request, f"Dropbox upload failed: {result['error']}")
                return JsonResponse({'error': result['error']}, status=500)
        else:
            return JsonResponse({'error': str(form.errors)}, status=400)
    else:
        form = ELibraryPDFForm()
    return render(request, 'elibrary/upload_pdf.html', {'form': form, 'course': course})


@login_required
def elibrary_pdf_delete(request, pk):
    pdf = get_object_or_404(ELibraryPDF, pk=pk)
    if request.method == 'POST':
        if pdf.dropbox_path:
            DropboxManager.delete_file(pdf.dropbox_path)
        pdf.delete()
        messages.success(request, 'PDF deleted successfully!')
    return redirect('elibrary_dashboard')


def get_or_create_setting(model, defaults=None):
    setting, _ = model.objects.get_or_create(id=1, defaults=defaults or {})
    return setting


# ── Settings pages (admin) ─────────────────────────────────────────────────────────
@login_required
def navbar_custom(request):
    setting = get_or_create_setting(NavbarSetting)
    if request.method == 'POST':
        form = NavbarSettingForm(request.POST, request.FILES, instance=setting)
        if form.is_valid():
            form.save()
            cache.delete('navbar_setting')
            messages.success(request, 'Navbar settings updated successfully!')
            return redirect('dashboard')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = NavbarSettingForm(instance=setting)
    return render(request, 'navbar.html', {'form': form})


@login_required
def banner_custom(request):
    desktop_banners = BannerSetting.objects.filter(banner_type='desktop').order_by('order')
    mobile_banners  = BannerSetting.objects.filter(banner_type='mobile').order_by('order')
    upload_form     = BannerUploadForm()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'upload':
            upload_form = BannerUploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                BannerSetting.objects.create(image=upload_form.cleaned_data['image'], banner_type=upload_form.cleaned_data['banner_type'], is_active=True)
                messages.success(request, 'Banner uploaded successfully!')
                return redirect('banner_custom')
            messages.error(request, 'Please select a valid image.')
        elif action == 'toggle':
            banner = get_object_or_404(BannerSetting, pk=request.POST.get('banner_id'))
            banner.is_active = not banner.is_active
            banner.save()
            messages.success(request, f"Banner {'activated' if banner.is_active else 'deactivated'}.")
            return redirect('banner_custom')
        elif action == 'delete':
            banner = get_object_or_404(BannerSetting, pk=request.POST.get('banner_id'))
            banner.image.delete(save=False)
            banner.delete()
            messages.success(request, 'Banner deleted successfully!')
            return redirect('banner_custom')
    return render(request, 'banner.html', {'upload_form': upload_form, 'desktop_banners': desktop_banners, 'mobile_banners': mobile_banners})


@login_required
def stats_custom(request):
    stats = StatsSetting.objects.all()
    if request.method == 'POST':
        form = StatsSettingForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Stats item added successfully!')
            return redirect('stats_custom')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = StatsSettingForm()
    return render(request, 'stats.html', {'stats': stats, 'form': form})


@login_required
def stats_edit(request, pk):
    stat = get_object_or_404(StatsSetting, pk=pk)
    if request.method == 'POST':
        form = StatsSettingForm(request.POST, instance=stat)
        if form.is_valid():
            form.save()
            messages.success(request, 'Stats item updated successfully!')
            return redirect('stats_custom')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = StatsSettingForm(instance=stat)
    return render(request, 'stats_edit.html', {'form': form, 'stat': stat})


@login_required
def stats_delete(request, pk):
    stat = get_object_or_404(StatsSetting, pk=pk)
    stat.delete()
    messages.success(request, 'Stats item deleted successfully!')
    return redirect('stats_custom')


@login_required
def about_custom(request):
    setting = AboutSetting.objects.first()
    if not setting:
        setting = AboutSetting.objects.create(
            heading='About BoosterNotes', text1='BoosterNotes provides exam-focused PDFs.',
            text2='', pdf_count='343+', books_count='500+', users_count='2456+', categories_count='10+',
            feature1_icon='fa-solid fa-bolt',     feature1_icon_color='#1a3a8f',
            feature1_title='Fast Download',        feature1_desc='Get instant access to PDF study material after purchase.',
            feature2_icon='fa-solid fa-bullseye',  feature2_icon_color='#28a745',
            feature2_title='Exam Targeted',        feature2_desc='Curated content for NEET, JEE, UPSC, SSC, and more.',
            feature3_icon='fa-solid fa-comments',  feature3_icon_color='#ffc107',
            feature3_title='Support',              feature3_desc='Support available on WhatsApp during working hours.',
        )
    if request.method == 'POST':
        form = AboutSettingForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            cache.delete('about_setting')
            messages.success(request, 'About section updated successfully!')
            return redirect('about_custom')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = AboutSettingForm(instance=setting)
    return render(request, 'about.html', {'form': form})


@login_required
def footer_custom(request):
    setting = FooterSetting.objects.first()
    if not setting:
        setting = FooterSetting.objects.create(brand_name='BoosterNotes', tagline='Smart Notes. Smart Rank.', description='Reliable study resources.', copyright_text='\u00a9 2026 BoosterNotes.')
    if request.method == 'POST':
        form = FooterSettingForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            cache.delete('footer_setting')
            messages.success(request, 'Footer updated!')
            return redirect('footer_custom')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = FooterSettingForm(instance=setting)
    return render(request, 'footer.html', {'form': form})


# ── Category admin ─────────────────────────────────────────────────────────────
@login_required
def category_list(request):
    categories = Category.objects.all()
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            category = form.save()
            cache.delete('home_categories')
            messages.success(request, f"Category '{category.name}' created!")
            return redirect('category_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = CategoryForm()
    return render(request, 'categories.html', {'categories': categories, 'form': form})


@login_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        name        = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        is_active   = request.POST.get('is_active') == 'on'
        if name:
            category.name        = name
            category.description = description
            category.is_active   = is_active
            if 'image' in request.FILES:
                if category.image and default_storage.exists(category.image.name):
                    default_storage.delete(category.image.name)
                category.image = request.FILES['image']
            category.save()
            cache.delete('home_categories')
            messages.success(request, f"Category '{category.name}' updated!")
        else:
            messages.error(request, 'Category name is required.')
    return redirect('category_list')


@login_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        if category.image and default_storage.exists(category.image.name):
            default_storage.delete(category.image.name)
        category.delete()
        cache.delete('home_categories')
        messages.success(request, 'Category deleted!')
    return redirect('category_list')


@login_required
def category_toggle_active(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        category.is_active = not category.is_active
        category.save()
        cache.delete('home_categories')
        status = 'activated' if category.is_active else 'deactivated'
        messages.success(request, f"Category '{category.name}' {status}!")
    return redirect('category_list')


# ── Coupons ───────────────────────────────────────────────────────────────────────
@login_required
def coupon_list(request):
    coupons = Coupon.objects.all()
    if request.method == 'POST':
        form = CouponForm(request.POST)
        if form.is_valid():
            coupon = form.save()
            messages.success(request, f"Coupon '{coupon.code}' created!")
            return redirect('coupon_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = CouponForm()
    return render(request, 'coupon.html', {'coupons': coupons, 'form': form})


@login_required
def coupon_delete(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    if request.method == 'POST':
        coupon.delete()
        messages.success(request, 'Coupon deleted!')
    return redirect('dashboard')


@login_required
def coupon_toggle_active(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    new_status = not coupon.is_active
    Coupon.objects.filter(pk=pk).update(is_active=new_status)
    messages.success(request, f"Coupon '{coupon.code}' {'activated' if new_status else 'deactivated'}!")
    return redirect('coupon_list')


def is_admin(user):
    return user.is_staff


# ── Notifications ──────────────────────────────────────────────────────────────
@login_required
@user_passes_test(is_admin)
def notifications_section(request):
    if request.method == 'POST':
        form = NotificationForm(request.POST)
        if form.is_valid():
            notification         = form.save(commit=False)
            notification.sent_at = timezone.now()
            notification.save()
            messages.success(request, 'Notification sent!')
            return redirect('notifications_section')
    else:
        form = NotificationForm()
    notifications       = Notification.objects.all()[:50]
    total_notifications = Notification.objects.count()
    sent_today          = Notification.objects.filter(sent_at__date=timezone.now().date()).count()
    return render(request, 'notification.html', {'title': 'Notifications', 'subtitle': 'Send notifications to users', 'form': form, 'notifications': notifications, 'total_notifications': total_notifications, 'sent_today': sent_today})


@login_required
@user_passes_test(is_admin)
def delete_notification(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id)
    if request.method == 'POST':
        notification.delete()
        messages.success(request, 'Notification deleted!')
        return redirect('notifications_section')
    return render(request, 'admin/confirm_delete.html', {'object': notification, 'action': 'delete notification', 'next_url': 'notifications_section'})


# ── User management ────────────────────────────────────────────────────────────
def add_user(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'User created!')
            return redirect('dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'add_user.html', {'form': form, 'title': 'Add New User', 'section': 'users'})


def edit_user(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f'User {user.username} updated!')
            return redirect('dashboard')
    else:
        form = CustomUserChangeForm(instance=user)
    return render(request, 'edit_user.html', {'form': form, 'user': user, 'title': f'Edit User: {user.username}', 'section': 'users'})


def delete_user(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'User {username} deleted!')
        return redirect('dashboard')
    return redirect('dashboard')


# ── HOME ────────────────────────────────────────────────────────────────────────────
def home(request):
    navbar = _get_navbar()
    if not navbar:
        navbar = NavbarSetting.objects.create(
            brand_name='BoosterNotes', tagline='Smart Notes. Smart Rank',
            search_placeholder='Search pdf courses, exams...',
            whatsapp_number='6350331916', whatsapp_hours='10 AM to 7 PM',
            coupon_text='\U0001f39f\ufe0f Apply Coupon'
        )
        cache.delete('navbar_setting')

    desktop_banners = BannerSetting.objects.filter(is_active=True, banner_type='desktop').order_by('order')
    mobile_banners  = BannerSetting.objects.filter(is_active=True, banner_type='mobile').order_by('order')
    if not desktop_banners.exists():
        BannerSetting.objects.create(banner_type='desktop', order=1, is_active=True)
        desktop_banners = BannerSetting.objects.filter(is_active=True, banner_type='desktop').order_by('order')
    if not mobile_banners.exists():
        BannerSetting.objects.create(banner_type='mobile', order=1, is_active=True)
        mobile_banners  = BannerSetting.objects.filter(is_active=True, banner_type='mobile').order_by('order')

    stats = StatsSetting.objects.filter(is_active=True).order_by('display_order')
    about  = _get_about()
    footer = _get_footer()

    coupon_qs = Coupon.objects.filter(is_active=True, expiry_date__gte=timezone.now().date()).annotate(remaining=F('usage_limit') - F('times_used')).filter(remaining__gt=0)
    if request.user.is_authenticated:
        used_ids = CouponUsage.objects.filter(user=request.user).values_list('coupon_id', flat=True)
        coupon_qs = coupon_qs.exclude(id__in=used_ids)
    active_coupons = coupon_qs.order_by('-created_at')[:6]

    categories = list(
        Category.objects.filter(is_active=True)
        .annotate(pdf_count=Count('elibrary_courses'))
        .order_by('name')
    )

    popular_pdfs = ELibraryModel.objects.filter(is_active=True).select_related('category').only('id', 'name', 'current_price', 'original_price', 'thumbnail', 'category_id').order_by('-created_at')[:8]

    hard_books = HardBook.objects.filter(is_active=True).prefetch_related(Prefetch('images', queryset=HardBookImage.objects.order_by('uploaded_at'))).order_by('-created_at')[:8]

    return render(request, 'index.html', {
        'navbar': navbar, 'site_settings': navbar,
        'desktop_banners': desktop_banners, 'mobile_banners': mobile_banners,
        'stats': stats, 'about': about, 'footer': footer,
        'categories': categories, 'active_coupons': active_coupons,
        'popular_pdfs': popular_pdfs, 'hard_books': hard_books,
        'cart_count': len(request.session.get('cart', {})),
    })


# ── Detail pages ───────────────────────────────────────────────────────────────────
def hard_book_detail(request, pk):
    book = get_object_or_404(
        HardBook.objects.prefetch_related(
            Prefetch('images', queryset=HardBookImage.objects.order_by('uploaded_at'))
        ),
        pk=pk, is_active=True
    )
    book_images = list(book.images.all())
    return render(request, 'hard_book_detail.html', {
        'book': book,
        'book_images': book_images,
        'navbar': _get_navbar(),
        'footer': _get_footer(),
        'cart_count': len(request.session.get('cart', {})),
    })


def elibrary_detail(request, pk):
    """
    Public course detail page.
    Passes a Django-hosted proxy URL for each accessible PDF so the
    browser NEVER talks to Dropbox directly.
    """
    from .models import Order, OrderItem
    course = get_object_or_404(
        ELibraryModel.objects.select_related('category').prefetch_related(
            Prefetch('pdfs', queryset=ELibraryPDF.objects.filter(is_active=True).order_by('uploaded_at'))
        ),
        pk=pk, is_active=True
    )

    is_purchased = False
    if request.user.is_authenticated:
        is_purchased = OrderItem.objects.filter(
            order__user=request.user,
            order__is_paid=True,
            item_type='pdf',
            item_id=str(pk)
        ).exists()

    uploaded_pdfs = list(course.pdfs.all())

    for idx, file in enumerate(uploaded_pdfs):
        file.is_first_pdf = (idx == 0)
        file.can_access   = is_purchased or file.is_demo or file.is_first_pdf
        if file.can_access:
            from django.urls import reverse
            file.preview_url  = reverse('elibrary_pdf_preview', args=[str(file.id)])
            file.download_url = reverse('elibrary_pdf_preview', args=[str(file.id)]) + '?dl=1'
        else:
            file.preview_url  = None
            file.download_url = None

    return render(request, 'elibrary_detail.html', {
        'pdf': course,
        'uploaded_pdfs': uploaded_pdfs,
        'is_purchased': is_purchased,
        'navbar': _get_navbar(),
        'footer': _get_footer(),
        'cart_count': len(request.session.get('cart', {})),
    })


# ── helpers ──────────────────────────────────────────────────────────────────────────
def _pdf_unavailable_response(request, pdf_name=''):
    """
    Return a polished 503 HTML page telling the user the PDF is
    temporarily unavailable.  No traceback, file path, or internal
    detail is ever exposed.
    """
    ctx = {
        'pdf_name' : pdf_name,
        'navbar'   : _get_navbar(),
        'footer'   : _get_footer(),
        'cart_count': len(request.session.get('cart', {})),
    }
    return render(request, 'pdf_unavailable.html', ctx, status=503)


# ── PDF Proxy / Streaming view ─────────────────────────────────────────────────────────
def elibrary_pdf_preview(request, pdf_id):
    """
    Stream a PDF file directly from Dropbox through Django.

    Access rules:
      - is_staff / is_superuser     -> always granted (admin preview)
      - is_demo=True or first PDF   -> public (no login needed)
      - all others                  -> authenticated + paid order required

    ?dl=1  -> Content-Disposition: attachment (download)
    default -> Content-Disposition: inline   (open in browser)
    """
    from .models import OrderItem

    pdf = get_object_or_404(ELibraryPDF, id=pdf_id, is_active=True)

    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        can_access = True
    else:
        first_pdf_id = (
            ELibraryPDF.objects
            .filter(course=pdf.course, is_active=True)
            .order_by('uploaded_at')
            .values_list('id', flat=True)
            .first()
        )
        is_first = str(first_pdf_id) == str(pdf_id)

        can_access = pdf.is_demo or is_first
        if not can_access:
            if not request.user.is_authenticated:
                raise Http404
            can_access = OrderItem.objects.filter(
                order__user=request.user,
                order__is_paid=True,
                item_type='pdf',
                item_id=str(pdf.course_id)
            ).exists()

    if not can_access:
        raise Http404

    force_download = request.GET.get('dl') == '1'
    raw_name   = pdf.pdf_name or 'document'
    filename   = raw_name if raw_name.lower().endswith('.pdf') else raw_name + '.pdf'
    disposition = (
        f'attachment; filename="{filename}"'
        if force_download else
        f'inline; filename="{filename}"'
    )

    if pdf.dropbox_path:
        try:
            dbx  = DropboxManager.get_dropbox_client()
            path = pdf.dropbox_path if pdf.dropbox_path.startswith('/') else '/' + pdf.dropbox_path
            _metadata, response = dbx.files_download(path)
            pdf_bytes = response.content
            http_response = HttpResponse(pdf_bytes, content_type='application/pdf')
            http_response['Content-Disposition'] = disposition
            http_response['Content-Length']      = str(len(pdf_bytes))
            return http_response
        except Exception:
            pass

    if pdf.pdf_file:
        try:
            from django.http import FileResponse
            response = FileResponse(pdf.pdf_file.open('rb'), content_type='application/pdf')
            response['Content-Disposition'] = disposition
            return response
        except Exception:
            pass

    return _pdf_unavailable_response(request, pdf_name=pdf.pdf_name)


# ── Apply Coupon (homepage "Save to Cart" button) ───────────────────────────────
@login_required
@require_POST
def apply_coupon(request):
    code         = request.POST.get('code', '').strip().upper()
    redirect_url = request.META.get('HTTP_REFERER', '/')
    if not code:
        messages.error(request, 'Please enter a coupon code.')
        return redirect(redirect_url)

    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        messages.error(request, '\u274c Invalid coupon code.')
        return redirect(redirect_url)

    if not coupon.is_active:
        messages.error(request, '\u274c This coupon is no longer active.')
        return redirect(redirect_url)
    if coupon.is_expired:
        messages.error(request, '\u274c This coupon has expired.')
        return redirect(redirect_url)
    if coupon.remaining_uses <= 0:
        messages.error(request, '\u274c This coupon has reached its usage limit.')
        return redirect(redirect_url)
    if CouponUsage.objects.filter(user=request.user, coupon=coupon).exists():
        messages.warning(request, '\u26a0\ufe0f You have already used this coupon.')
        return redirect(redirect_url)

    request.session['applied_coupon_id']     = coupon.id
    request.session['applied_coupon_code']   = coupon.code
    request.session['applied_coupon_amount'] = str(coupon.amount)
    messages.success(request, f"\u2705 Coupon '{coupon.code}' saved! \u20b9{coupon.amount} discount will apply at checkout.")
    return redirect(redirect_url)


# ── Admin Dashboard ─────────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You don't have permission.")
        return redirect('home')

    users = User.objects.only('id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'date_joined').order_by('-date_joined')
    total_users     = users.count()
    active_users    = users.filter(is_active=True).count()
    inactive_users  = users.filter(is_active=False).count()
    thirty_days_ago = datetime.now() - timedelta(days=30)
    new_users       = users.filter(date_joined__gte=thirty_days_ago).count()
    staff_users     = users.filter(is_staff=True).count()

    from .models import Order
    total_revenue    = Order.objects.filter(is_paid=True).aggregate(r=Sum('grand_total'))['r'] or 0
    completed_orders = Order.objects.filter(status='paid').count()
    pending_orders   = Order.objects.filter(status='pending').count()
    failed_orders    = Order.objects.filter(status='cancelled').count()
    recent_transactions = Order.objects.select_related('user').prefetch_related('items').order_by('-created_at')[:10]

    return render(request, 'admin_dashboard.html', {
        'users': users, 'total_users': total_users,
        'active_users': active_users, 'inactive_users': inactive_users,
        'new_users': new_users, 'staff_users': staff_users,
        'form': CustomUserCreationForm(),
        'total_revenue': total_revenue,
        'completed_orders': completed_orders,
        'pending_orders': pending_orders,
        'failed_orders': failed_orders,
        'recent_transactions': recent_transactions,
    })


# ── Auth ────────────────────────────────────────────────────────────────────────────
def user_login(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        email    = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password')
        try:
            user_obj = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            messages.error(request, 'No account found with that email address.')
            return redirect('login')
        user = authenticate(request, username=user_obj.username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, 'Login successful!')
            return redirect(request.POST.get('next') or request.GET.get('next') or 'home')
        messages.error(request, 'Incorrect password. Please try again.')
        return redirect('login')
    return render(request, 'login.html')


def signup(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        full_name = request.POST.get('name', '').strip()
        email     = request.POST.get('email', '').strip().lower()
        password  = request.POST.get('password', '').strip()

        if not full_name or not email or not password:
            messages.error(request, 'All fields are required.')
            return redirect('signup')

        if len(password) < 6:
            messages.error(request, 'Password must be at least 6 characters.')
            return redirect('signup')

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'An account with this email already exists. Please login.')
            return redirect('signup')

        username = email

        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=full_name,
                is_staff=False,
                is_superuser=False,
            )
            login(request, user)
            messages.success(request, f'Welcome, {full_name}! Your account has been created.')
            return redirect('home')
        except Exception:
            messages.error(request, 'Something went wrong. Please try again.')
            return redirect('signup')

    return render(request, 'signup.html')


# ── Custom 404 ── works even with DEBUG=True ──────────────────────────────────────
def custom_404_view(request, unknown_path=None):
    return render(request, '404.html', status=404)
