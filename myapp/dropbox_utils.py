import os
import re
import time
import dropbox
from django.conf import settings
from dropbox import Dropbox, exceptions
from dropbox.exceptions import ApiError


# ── Canonical path builder ─────────────────────────────────────────────────────────
class DropboxPaths:
    """
    Single source of truth for every Dropbox folder/path used in the app.

    Dropbox structure produced:

        BoosterNotes/
        ├── Backups/
        │   ├── db_latest.sqlite3
        │   └── db_20260721_153000.sqlite3
        ├── eLibrary/
        │   ├── <Course Name>/
        │   │   ├── Images/
        │   │   │   └── thumbnail.jpg
        │   │   └── PDFs/
        │   │       ├── Chapter 1.pdf
        │   │       └── ...
        │   └── <Course Name 2>/
        │       └── ...
        └── HardBooks/
            └── Images/
                └── ...
    """

    ROOT = "BoosterNotes"

    # ─ top-level folders ───────────────────────────────────────────────────────────────
    BACKUPS   = f"{ROOT}/Backups"
    ELIBRARY  = f"{ROOT}/eLibrary"
    HARDBOOKS = f"{ROOT}/HardBooks"

    @staticmethod
    def _slug(name: str) -> str:
        """Turn an arbitrary string into a safe Dropbox folder name."""
        safe = re.sub(r'[\\/:*?"<>|]+', '_', name).strip('. ')
        safe = re.sub(r'_+', '_', safe)
        return safe or 'Unnamed'

    # ─ backup paths ────────────────────────────────────────────────────────────────
    @classmethod
    def backup_latest(cls) -> str:
        return f"/{cls.BACKUPS}/db_latest.sqlite3"

    @classmethod
    def backup_timestamped(cls, timestamp: str) -> str:
        return f"/{cls.BACKUPS}/db_{timestamp}.sqlite3"

    @classmethod
    def backups_folder(cls) -> str:
        return cls.BACKUPS

    # ─ eLibrary paths ───────────────────────────────────────────────────────────────
    @classmethod
    def elibrary_pdfs(cls, course_name: str) -> str:
        return f"{cls.ELIBRARY}/{cls._slug(course_name)}/PDFs"

    @classmethod
    def elibrary_images(cls, course_name: str) -> str:
        return f"{cls.ELIBRARY}/{cls._slug(course_name)}/Images"

    # ─ HardBook paths ───────────────────────────────────────────────────────────────
    @classmethod
    def hardbooks_images(cls) -> str:
        return f"{cls.HARDBOOKS}/Images"


class DropboxManager:
    """Handle all Dropbox operations."""

    @staticmethod
    def get_dropbox_client():
        return Dropbox(
            oauth2_refresh_token=settings.DROPBOX_REFRESH_TOKEN,
            app_key=settings.DROPBOX_APP_KEY,
            app_secret=settings.DROPBOX_APP_SECRET,
        )

    @staticmethod
    def _read_chunk(file_obj, size):
        return file_obj.read(size)

    @staticmethod
    def _upload_with_retry(fn, *args, retries=3, backoff=2, **kwargs):
        last_exc = None
        for attempt in range(retries):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(backoff * (attempt + 1))
        raise last_exc

    @staticmethod
    def _get_file_size(file_obj) -> int:
        """
        Robustly determine the byte size of any file-like object.

        Works with:
          - Django InMemoryUploadedFile / TemporaryUploadedFile  (.size attr)
          - django.core.files.base.ContentFile  (.size may be set manually)
          - Raw io.BytesIO / any seekable stream  (seek to end)
        """
        # 1. Prefer an explicit .size attribute (set by Django or by the caller)
        size = getattr(file_obj, 'size', None)
        if size is not None:
            return int(size)

        # 2. Fallback: seek to end, record position, seek back
        try:
            current = file_obj.tell()
            file_obj.seek(0, 2)       # SEEK_END
            size = file_obj.tell()
            file_obj.seek(current)    # restore
            return size
        except Exception:
            pass

        # 3. Last resort: read all bytes, then seek back
        file_obj.seek(0)
        data = file_obj.read()
        file_obj.seek(0)
        return len(data)

    # ── public API ──────────────────────────────────────────────────────────────────
    @staticmethod
    def get_temporary_link(dropbox_path):
        """
        Return a short-lived (~4 hours) direct HTTPS link to a Dropbox file.
        Returns the URL string on success, or None on failure.
        """
        try:
            dbx = DropboxManager.get_dropbox_client()
            if not dropbox_path.startswith('/'):
                dropbox_path = '/' + dropbox_path.lstrip('/')
            result = dbx.files_get_temporary_link(dropbox_path)
            return result.link
        except Exception:
            return None

    @staticmethod
    def upload_file(file_obj, file_name, folder_path=None):
        """
        Upload a file to Dropbox.

        Uses simple upload for files <= 4 MB, chunked upload sessions for
        larger files.  Works with any file-like object (InMemoryUploadedFile,
        TemporaryUploadedFile, ContentFile, BytesIO, etc.).

        `folder_path` should be a path string WITHOUT a leading slash.

        Returns a dict: {success, dropbox_path, link, message | error}.
        """
        try:
            dbx = DropboxManager.get_dropbox_client()

            if folder_path is None:
                folder_path = settings.DROPBOX_FOLDER

            folder_path = str(folder_path).strip("/")
            file_name   = os.path.basename(file_name)
            full_path   = f"/{folder_path}/{file_name}"

            file_obj.seek(0)
            # ── Use the robust helper — never crashes on ContentFile ─────────────
            file_size  = DropboxManager._get_file_size(file_obj)
            file_obj.seek(0)          # ensure we're back at the start
            CHUNK_SIZE = 4 * 1024 * 1024   # 4 MB

            if file_size <= CHUNK_SIZE:
                # ── simple upload ──────────────────────────────────────────────────
                DropboxManager._upload_with_retry(
                    dbx.files_upload,
                    file_obj.read(),
                    full_path,
                    mode=dropbox.files.WriteMode.overwrite,
                )
            else:
                # ── chunked upload session ───────────────────────────────────────
                first_chunk = DropboxManager._read_chunk(file_obj, CHUNK_SIZE)
                session = DropboxManager._upload_with_retry(
                    dbx.files_upload_session_start, first_chunk
                )
                offset = len(first_chunk)

                cursor = dropbox.files.UploadSessionCursor(
                    session_id=session.session_id,
                    offset=offset,
                )
                commit = dropbox.files.CommitInfo(
                    path=full_path,
                    mode=dropbox.files.WriteMode.overwrite,
                )

                while offset < file_size:
                    remaining = file_size - offset
                    chunk     = DropboxManager._read_chunk(
                        file_obj, min(CHUNK_SIZE, remaining)
                    )
                    is_last = (offset + len(chunk)) >= file_size

                    if is_last:
                        DropboxManager._upload_with_retry(
                            dbx.files_upload_session_finish,
                            chunk, cursor, commit,
                        )
                    else:
                        DropboxManager._upload_with_retry(
                            dbx.files_upload_session_append_v2,
                            chunk, cursor,
                        )
                        cursor.offset += len(chunk)

                    offset += len(chunk)

            # ── create / fetch shared link ─────────────────────────────────────
            try:
                shared = dbx.sharing_create_shared_link_with_settings(full_path)
                link   = shared.url
            except dropbox.exceptions.ApiError:
                try:
                    links = dbx.sharing_list_shared_links(path=full_path, direct_only=True)
                    link  = links.links[0].url if links.links else f"https://www.dropbox.com/home{full_path}"
                except Exception:
                    link = f"https://www.dropbox.com/home{full_path}"
            except Exception:
                link = f"https://www.dropbox.com/home{full_path}"

            return {
                "success":      True,
                "dropbox_path": full_path,
                "link":         link,
                "message":      "File uploaded successfully",
            }

        except exceptions.ApiError as e:
            return {
                "success":      False,
                "error":        f"Dropbox API error: {str(e)}",
                "dropbox_path": None,
                "link":         None,
            }
        except Exception as e:
            return {
                "success":      False,
                "error":        str(e),
                "dropbox_path": None,
                "link":         None,
            }

    @staticmethod
    def delete_file(dropbox_path):
        """Delete a file from Dropbox."""
        try:
            dbx = DropboxManager.get_dropbox_client()
            if not dropbox_path.startswith("/"):
                dropbox_path = "/" + dropbox_path.lstrip("/")
            dbx.files_delete_v2(dropbox_path)
            return {"success": True, "message": "File deleted successfully"}
        except Exception as e:
            return {"success": False, "error": str(e)}
