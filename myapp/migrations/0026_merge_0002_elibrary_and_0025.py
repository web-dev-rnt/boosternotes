# Merge migration: resolves the two leaf nodes in the migration graph:
#   - 0002_elibrary_dropbox_thumbnail_path  (stray branch off 0001_initial)
#   - 0025_elibrarypdf_display_order        (main chain tip)
# This is equivalent to running: python manage.py makemigrations --merge

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0002_elibrary_dropbox_thumbnail_path'),
        ('myapp', '0025_elibrarypdf_display_order'),
    ]

    operations = [
        # No operations needed — this migration only merges two branches.
    ]
