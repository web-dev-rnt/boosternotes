# Generated manually — adds cached Dropbox URL fields to ELibraryModel and HardBookImage
# so thumbnail_url / image_url properties no longer call Dropbox API on every page load.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0025_elibrarypdf_display_order'),
    ]

    operations = [
        # ── ELibraryModel ─────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='elibrarymodel',
            name='dropbox_thumbnail_url_cached',
            field=models.CharField(
                blank=True,
                max_length=1000,
                null=True,
                verbose_name='Cached Dropbox Thumbnail URL',
            ),
        ),
        migrations.AddField(
            model_name='elibrarymodel',
            name='dropbox_thumbnail_url_expires',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Cached Thumbnail URL Expiry',
            ),
        ),
        # ── HardBookImage ─────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='hardbookimage',
            name='dropbox_image_url_cached',
            field=models.CharField(
                blank=True,
                max_length=1000,
                null=True,
                verbose_name='Cached Dropbox Image URL',
            ),
        ),
        migrations.AddField(
            model_name='hardbookimage',
            name='dropbox_image_url_expires',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Cached Image URL Expiry',
            ),
        ),
    ]
