"""
Safe idempotent migration — adds ALL Dropbox-related columns that models.py
defines but that may be missing from the live database.

Uses RunPython + PRAGMA table_info() so each ALTER TABLE is only issued when
the column is genuinely absent. Safe to run on:
  - Fresh databases          (all columns missing → all added)
  - Partially-migrated DBs   (some columns present → only missing ones added)
  - Fully-migrated DBs       (all columns present → nothing happens)

Columns managed (all nullable/blank):
  myapp_elibrarymodel  .dropbox_thumbnail_path        VARCHAR(500)
  myapp_elibrarymodel  .dropbox_thumbnail_url_cached  VARCHAR(1000)
  myapp_elibrarymodel  .dropbox_thumbnail_url_expires DATETIME
  myapp_hardbookimage  .dropbox_path                  VARCHAR(500)
  myapp_hardbookimage  .dropbox_image_url_cached      VARCHAR(1000)
  myapp_hardbookimage  .dropbox_image_url_expires     DATETIME
"""

from django.db import migrations, connection


def _existing_columns(table):
    """Return a set of column names already present in *table*."""
    with connection.cursor() as cursor:
        cursor.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cursor.fetchall()}


def add_columns_safe(apps, schema_editor):
    db = schema_editor.connection

    specs = [
        # ── ELibraryModel ──────────────────────────────────────────────────
        ("myapp_elibrarymodel", "dropbox_thumbnail_path",        "VARCHAR(500) NULL"),
        ("myapp_elibrarymodel", "dropbox_thumbnail_url_cached",  "VARCHAR(1000) NULL"),
        ("myapp_elibrarymodel", "dropbox_thumbnail_url_expires", "DATETIME NULL"),
        # ── HardBookImage ──────────────────────────────────────────────────
        ("myapp_hardbookimage", "dropbox_path",                  "VARCHAR(500) NULL"),
        ("myapp_hardbookimage", "dropbox_image_url_cached",      "VARCHAR(1000) NULL"),
        ("myapp_hardbookimage", "dropbox_image_url_expires",     "DATETIME NULL"),
    ]

    for table, column, col_type in specs:
        existing = _existing_columns(table)
        if column not in existing:
            with db.cursor() as cursor:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                )


def noop_reverse(apps, schema_editor):
    # Intentionally do not drop columns on rollback — avoids data loss.
    pass


class Migration(migrations.Migration):

    dependencies = [
        # All three 0026/0027 files are no-ops; depending on all of them
        # ensures this migration runs last regardless of which subset is
        # already recorded in django_migrations on any given environment.
        ('myapp', '0026_cache_dropbox_image_urls'),
        ('myapp', '0026_merge_0002_elibrary_and_0025'),
        ('myapp', '0027_cache_dropbox_image_urls'),
    ]

    operations = [
        migrations.RunPython(add_columns_safe, reverse_code=noop_reverse),
    ]
