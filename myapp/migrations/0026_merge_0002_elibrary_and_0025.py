# Merge migration: joins the 0002_elibrary_dropbox_thumbnail_path branch
# (now a no-op stub) with the main chain tip at 0025_elibrarypdf_display_order.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0002_elibrary_dropbox_thumbnail_path'),
        ('myapp', '0025_elibrarypdf_display_order'),
    ]

    operations = [
        # No operations needed — this migration only merges two branches.
    ]
