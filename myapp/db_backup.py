import os
import dropbox
from datetime import datetime
from django.conf import settings
from .dropbox_utils import DropboxPaths


def get_dropbox_client():
    return dropbox.Dropbox(
        oauth2_refresh_token=settings.DROPBOX_REFRESH_TOKEN,
        app_key=settings.DROPBOX_APP_KEY,
        app_secret=settings.DROPBOX_APP_SECRET
    )


def get_db_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'db.sqlite3'
    )


def backup_to_dropbox():
    """
    Uploads db.sqlite3 to Dropbox under BoosterNotes/Backups/.

    Saves:
      1. BoosterNotes/Backups/db_latest.sqlite3
      2. BoosterNotes/Backups/db_<timestamp>.sqlite3

    Returns the timestamp string on success.
    """
    dbx = get_dropbox_client()
    db_path = get_db_path()

    with open(db_path, 'rb') as f:
        data = f.read()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    dbx.files_upload(
        data,
        DropboxPaths.backup_latest(),
        mode=dropbox.files.WriteMode.overwrite
    )

    dbx.files_upload(
        data,
        DropboxPaths.backup_timestamped(timestamp),
        mode=dropbox.files.WriteMode.add
    )

    return timestamp


def restore_from_dropbox(history_filename=None):
    """
    Restores db.sqlite3 from Dropbox.
    If history_filename is provided, restores that specific backup.
    Otherwise restores the latest backup.
    """
    dbx = get_dropbox_client()
    db_path = get_db_path()

    if history_filename:
        path = f"/{DropboxPaths.BACKUPS}/{history_filename}"
    else:
        path = DropboxPaths.backup_latest()

    _, res = dbx.files_download(path)

    with open(db_path, 'wb') as f:
        f.write(res.content)


def list_backups():
    """
    Returns a list of timestamped backup filenames from BoosterNotes/Backups/,
    sorted newest first. Excludes the rolling 'db_latest.sqlite3' entry.
    """
    dbx = get_dropbox_client()
    folder = f"/{DropboxPaths.BACKUPS}"
    try:
        result = dbx.files_list_folder(folder)
        files = [
            entry.name
            for entry in result.entries
            if (
                isinstance(entry, dropbox.files.FileMetadata)
                and entry.name != 'db_latest.sqlite3'
            )
        ]
        return sorted(files, reverse=True)
    except dropbox.exceptions.ApiError:
        return []
