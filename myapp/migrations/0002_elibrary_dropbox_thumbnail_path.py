# This migration originally referenced a model 'elibrarybody' that did not exist
# in the initial schema. ELibraryModel was introduced in 0013_elibrarymodel_elibrarypdf.
# The operations have been replaced with no-ops so that environments where this
# migration was previously recorded as applied continue to work without errors.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0001_initial'),
    ]

    operations = [
        # No operations — original operations removed because they referenced
        # 'elibrarybody' and 'elibrarymodel' which did not exist at this point
        # in the migration chain (both were created in migration 0013).
    ]
