from datetime import datetime, timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
import uuid


class HardBook(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, verbose_name="Book Title")
    description = models.TextField(verbose_name="Description")
    original_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="Original Price")
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="Sale Price")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Hard Book"
        verbose_name_plural = "Hard Books"

    def __str__(self):
        return self.title


class HardBookImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    book = models.ForeignKey(HardBook, on_delete=models.CASCADE, related_name='images', verbose_name="Book")
    image = models.ImageField(upload_to='hardbooks/images/', verbose_name="Book Image")
    dropbox_path = models.CharField(max_length=500, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']
        verbose_name = "Hard Book Image"
        verbose_name_plural = "Hard Book Images"

    def __str__(self):
        return f"{self.book.title} - Image"


class SiteSetting(models.Model):
    key = models.CharField(max_length=100, unique=True, verbose_name="Setting Key")
    value = models.TextField(blank=True, null=True, verbose_name="Setting Value")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']
        verbose_name = "Site Setting"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return f"{self.key} = {self.value[:50]}..." if self.value and len(self.value) > 50 else f"{self.key} = {self.value}"


class NavbarSetting(models.Model):
    brand_name = models.CharField(max_length=100, default="BoosterNotes", verbose_name="Brand Name")
    tagline = models.CharField(max_length=100, default="Smart Notes. Smart Rank", verbose_name="Tagline")
    logo = models.ImageField(upload_to='logos/', blank=True, null=True, verbose_name="Logo Image")
    favicon = models.ImageField(upload_to='favicons/', blank=True, null=True, verbose_name="Favicon")
    search_placeholder = models.CharField(max_length=200, default="Search pdf courses, exams...", verbose_name="Search Placeholder")
    whatsapp_number = models.CharField(max_length=20, default="6350331916", verbose_name="WhatsApp Number")
    whatsapp_hours = models.CharField(max_length=50, default="10 AM to 7 PM", verbose_name="WhatsApp Hours")
    coupon_text = models.CharField(max_length=100, default="\U0001f39f\ufe0f Apply Coupon", verbose_name="Coupon Button Text")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")

    class Meta:
        verbose_name = "Navbar Setting"
        verbose_name_plural = "Navbar Settings"

    def __str__(self):
        return f"Navbar - {self.brand_name}"


class BannerSetting(models.Model):
    BANNER_TYPE_CHOICES = [('desktop', 'Desktop'), ('mobile', 'Mobile')]
    image = models.ImageField(upload_to='banners/', verbose_name="Banner Image", blank=True, null=True)
    banner_type = models.CharField(max_length=10, choices=BANNER_TYPE_CHOICES, default='desktop', verbose_name="Banner Type")
    order = models.PositiveIntegerField(default=0, verbose_name="Display Order")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Banner Setting"
        verbose_name_plural = "Banner Settings"
        ordering = ['banner_type', 'order']

    def __str__(self):
        return f"{self.get_banner_type_display()} Banner #{self.pk}"


class StatsSetting(models.Model):
    icon = models.CharField(max_length=50, verbose_name="Icon (Font Awesome class)")
    icon_color = models.CharField(max_length=20, default="#1a3a8f", verbose_name="Icon Color (hex code)")
    value = models.CharField(max_length=50, verbose_name="Value (e.g., 343, 500+)")
    title = models.CharField(max_length=100, verbose_name="Title")
    note = models.CharField(max_length=200, blank=True, null=True, verbose_name="Note/Subtitle")
    display_order = models.PositiveIntegerField(default=0, verbose_name="Display Order")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")

    class Meta:
        ordering = ['display_order', 'id']
        verbose_name = "Stats Setting"
        verbose_name_plural = "Stats Settings"

    def __str__(self):
        return f"{self.title} - {self.value}"


class AboutSetting(models.Model):
    heading = models.CharField(max_length=200, default="About BoosterNotes", verbose_name="Heading")
    text1 = models.TextField(verbose_name="First Paragraph")
    text2 = models.TextField(blank=True, null=True, verbose_name="Second Paragraph (optional)")
    pdf_count = models.CharField(max_length=20, default="343+", verbose_name="PDF Resources Count")
    books_count = models.CharField(max_length=20, default="500+", verbose_name="Books Count")
    users_count = models.CharField(max_length=20, default="2456+", verbose_name="Users Count")
    categories_count = models.CharField(max_length=20, default="10+", verbose_name="Exam Categories Count")
    feature1_icon = models.CharField(max_length=50, default="fa-solid fa-bolt")
    feature1_icon_color = models.CharField(max_length=20, default="#1a3a8f")
    feature1_title = models.CharField(max_length=100, default="Fast Download")
    feature1_desc = models.TextField(default="Get instant access to PDF study material after purchase.")
    feature2_icon = models.CharField(max_length=50, default="fa-solid fa-bullseye")
    feature2_icon_color = models.CharField(max_length=20, default="#28a745")
    feature2_title = models.CharField(max_length=100, default="Exam Targeted")
    feature2_desc = models.TextField(default="Curated content for NEET, JEE, UPSC, SSC, and more.")
    feature3_icon = models.CharField(max_length=50, default="fa-solid fa-comments")
    feature3_icon_color = models.CharField(max_width=20, default="#ffc107")
    feature3_title = models.CharField(max_length=100, default="Support")
    feature3_desc = models.TextField(default="Support available on WhatsApp during working hours.")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "About Setting"
        verbose_name_plural = "About Settings"
        ordering = ['id']

    def __str__(self):
        return "About Section"


class FooterSetting(models.Model):
    brand_name = models.CharField(max_length=100, default="BoosterNotes")
    tagline = models.CharField(max_length=200, default="Smart Notes. Smart Rank.")
    description = models.TextField(default="Reliable study resources for competitive exams.")
    quick_links_title = models.CharField(max_length=100, default="Quick Links")
    support_title = models.CharField(max_length=100, default="Support")
    contact_title = models.CharField(max_length=100, default="Contact")
    whatsapp_contact = models.CharField(max_length=50, default="WhatsApp: 6350331916")
    hours_contact = models.CharField(max_length=50, default="10 AM - 7 PM")
    copyright_text = models.CharField(max_length=200, default="\u00a9 2026 BoosterNotes. All rights reserved.")
    social_facebook = models.CharField(max_length=200, blank=True, null=True)
    social_linkedin = models.CharField(max_length=200, blank=True, null=True)
    social_instagram = models.CharField(max_length=200, blank=True, null=True)
    social_youtube = models.CharField(max_length=200, blank=True, null=True)
    social_facebook_color = models.CharField(max_length=20, default="#1877f2")
    social_linkedin_color = models.CharField(max_length=20, default="#0a66c2")
    social_instagram_color = models.CharField(max_length=20, default="#e4405f")
    social_youtube_color = models.CharField(max_length=20, default="#ff0000")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Footer Setting"
        verbose_name_plural = "Footer Settings"
        ordering = ['id']

    def __str__(self):
        return "Footer Setting"


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Category Name")
    image = models.ImageField(upload_to='categories/', blank=True, null=True, verbose_name="Category Image")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

    @property
    def image_url(self):
        if self.image and hasattr(self.image, 'url'):
            return self.image.url
        return None


class Notification(models.Model):
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.URLField(max_length=500, blank=True, null=True)
    sent_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return self.title


class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="Coupon Code")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Discount Amount")
    expiry_date = models.DateField(verbose_name="Expiry Date")
    usage_limit = models.PositiveIntegerField(default=1, verbose_name="Usage Limit")
    times_used = models.PositiveIntegerField(default=0, editable=False)
    is_active = models.BooleanField(default=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Coupon"
        verbose_name_plural = "Coupons"

    def __str__(self):
        return f"{self.code} - \u20b9{self.amount}"

    def save(self, *args, **kwargs):
        if self.expiry_date and self.expiry_date < timezone.now().date():
            self.is_active = False
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return self.expiry_date < timezone.now().date()

    @property
    def remaining_uses(self):
        return max(0, self.usage_limit - self.times_used)


class CouponUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coupon_usages')
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='usages')
    used_at = models.DateTimeField(auto_now_add=True)
    discount_applied = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    class Meta:
        ordering = ['-used_at']
        verbose_name = "Coupon Usage"
        verbose_name_plural = "Coupon Usages"
        unique_together = ('user', 'coupon')

    def __str__(self):
        return f"{self.user.username} - {self.coupon.code}"


class ELibraryModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name="Course Name")
    description = models.TextField(verbose_name="Description")
    original_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="Original Price")
    current_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="Current Price")
    thumbnail = models.ImageField(upload_to='elibrary/thumbnails/', verbose_name="Thumbnail Image")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, blank=True, null=True, related_name='elibrary_courses')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "E-Library Item"
        verbose_name_plural = "E-Library Items"

    def __str__(self):
        return self.name


class ELibraryPDF(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(ELibraryModel, on_delete=models.CASCADE, related_name='pdfs')
    pdf_name = models.CharField(max_length=200)
    pdf_file = models.FileField(upload_to='elibrary/pdfs/')
    dropbox_path = models.CharField(max_length=500, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField(
        default=False,
        verbose_name='Free Demo',
        help_text='Tick this to make the PDF freely accessible to all visitors as a demo preview.'
    )
    display_order = models.PositiveIntegerField(default=0, verbose_name='Display Order')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', 'uploaded_at']
        verbose_name = "E-Library PDF"
        verbose_name_plural = "E-Library PDFs"

    def __str__(self):
        return f"{self.pdf_name} - {self.course.name}"


# ─────────────────────────────────────────────────────────────────────────────
# ORDER MODELS
# ─────────────────────────────────────────────────────────────────────────────

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('paid',       'Paid'),
        ('processing', 'Processing'),
        ('shipped',    'Shipped'),
        ('delivered',  'Delivered'),
        ('cancelled',  'Cancelled'),
        ('refunded',   'Refunded'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('razorpay', 'Razorpay'),
        ('cod',      'Cash on Delivery'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=20, unique=True, editable=False)

    # Customer details
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    mobile = models.CharField(max_length=15)

    # Delivery address (for physical books)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    country = models.CharField(max_length=100, default='India')

    # Pricing
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)

    # Payment
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='razorpay')
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=200, blank=True, null=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Order"
        verbose_name_plural = "Orders"

    def __str__(self):
        return f"Order #{self.order_number} - {self.full_name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            import random, string
            self.order_number = 'BN' + ''.join(random.choices(string.digits, k=8))
        super().save(*args, **kwargs)

    @property
    def has_physical_items(self):
        return self.items.filter(item_type='book').exists()

    @property
    def has_digital_items(self):
        return self.items.filter(item_type='pdf').exists()


class OrderItem(models.Model):
    ITEM_TYPE_CHOICES = [
        ('pdf',  'E-Library PDF'),
        ('book', 'Hard Copy Book'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    item_type = models.CharField(max_length=10, choices=ITEM_TYPE_CHOICES)
    item_id = models.CharField(max_length=100)      # UUID stored as string
    item_name = models.CharField(max_length=300)
    item_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"

    def __str__(self):
        return f"{self.item_name} x{self.quantity}"
