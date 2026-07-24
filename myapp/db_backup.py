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


def backup_images_to_dropbox(dbx, timestamp):
    """
    Copies all image files from eLibrary and HardBooks/Images into
    BoosterNotes/Backups/images_<timestamp>/ on Dropbox.
    Silently skips folders that don't exist yet.
    """
    image_folders = [
        f"/{DropboxPaths.ELIBRARY}",
        f"/{DropboxPaths.HARDBOOKS}/Images",
    ]
    backup_root = f"/{DropboxPaths.BACKUPS}/images_{timestamp}"
    root_lower  = f"/{DropboxPaths.ROOT.lower()}"

    for folder in image_folders:
        try:
            result = dbx.files_list_folder(folder, recursive=True)
            entries = list(result.entries)

            # Handle pagination
            while result.has_more:
                result = dbx.files_list_folder_continue(result.cursor)
                entries.extend(result.entries)

            for entry in entries:
                if not isinstance(entry, dropbox.files.FileMetadata):
                    continue
                try:
                    _, res = dbx.files_download(entry.path_lower)
                    # Rebuild destination path preserving subfolder structure
                    relative = entry.path_lower.replace(root_lower, "", 1)
                    dest = f"{backup_root}{relative}"
                    dbx.files_upload(
                        res.content,
                        dest,
                        mode=dropbox.files.WriteMode.overwrite
                    )
                except Exception:
                    # Skip individual file errors (don't abort entire backup)
                    pass

        except dropbox.exceptions.ApiError:
            # Folder doesn't exist yet — skip silently
            pass


def backup_to_dropbox():
    """
    Uploads db.sqlite3 AND all Dropbox-stored images to Dropbox under
    BoosterNotes/Backups/.

    Saves:
      1. BoosterNotes/Backups/db_latest.sqlite3          (always overwritten)
      2. BoosterNotes/Backups/db_<timestamp>.sqlite3     (timestamped history)
      3. BoosterNotes/Backups/images_<timestamp>/        (all eLibrary + HardBook images)

    Returns the timestamp string on success.
    """
    dbx = get_dropbox_client()
    db_path = get_db_path()

    with open(db_path, 'rb') as f:
        data = f.read()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 1. Overwrite rolling latest DB
    dbx.files_upload(
        data,
        DropboxPaths.backup_latest(),
        mode=dropbox.files.WriteMode.overwrite
    )

    # 2. Save timestamped DB history copy
    dbx.files_upload(
        data,
        DropboxPaths.backup_timestamped(timestamp),
        mode=dropbox.files.WriteMode.add
    )

    # 3. Back up all images stored on Dropbox
    backup_images_to_dropbox(dbx, timestamp)

    return timestamp


def restore_from_dropbox(history_filename=None):
    """
    Restores db.sqlite3 from Dropbox.
    If history_filename is provided, restores that specific backup.
    Otherwise restores the latest backup.

    NOTE: Images are already live on Dropbox and do not need to be restored
    separately — only the database file needs to be replaced.
    If you want to also restore images from a specific timestamped backup,
    use restore_images_from_dropbox(timestamp) manually.
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


def restore_images_from_dropbox(timestamp):
    """
    Optional: Restores images from a specific timestamped image backup
    (BoosterNotes/Backups/images_<timestamp>/) back to their original
    BoosterNotes/eLibrary/ and BoosterNotes/HardBooks/ locations.

    Call this only if you need to roll back images to match a specific
    database restore point.
    """
    dbx = get_dropbox_client()
    backup_folder = f"/{DropboxPaths.BACKUPS}/images_{timestamp}"
    backup_lower  = backup_folder.lower()
    root_prefix   = f"/{DropboxPaths.ROOT.lower()}"

    try:
        result = dbx.files_list_folder(backup_folder, recursive=True)
        entries = list(result.entries)

        while result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
            entries.extend(result.entries)

        for entry in entries:
            if not isinstance(entry, dropbox.files.FileMetadata):
                continue
            try:
                _, res = dbx.files_download(entry.path_lower)
                # Strip the backup prefix to get the original path
                relative = entry.path_lower.replace(backup_lower, "", 1)
                dest = f"{root_prefix}{relative}"
                dbx.files_upload(
                    res.content,
                    dest,
                    mode=dropbox.files.WriteMode.overwrite
                )
            except Exception:
                pass

    except dropbox.exceptions.ApiError:
        pass


def list_backups():
    """
    Returns a list of timestamped backup filenames from BoosterNotes/Backups/,
    sorted newest first.  Excludes the rolling 'db_latest.sqlite3' entry.
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
