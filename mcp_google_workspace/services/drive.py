import base64
import binascii
import io
import logging
import mimetypes
from typing import Any

from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.discovery import build
from ..auth.credentials import get_google_credentials

logger = logging.getLogger(__name__)


class DriveService:
    def __init__(self):
        self._service = None

    @property
    def service(self):
        if self._service is None:
            creds = get_google_credentials()
            self._service = build("drive", "v3", credentials=creds)
        return self._service

    def search_files(self, query: str, page_size: int = 10, shared_drive_id: str | None = None) -> list[dict]:
        page_size = max(1, min(page_size, 1000))
        params = {
            "q": query,
            "pageSize": page_size,
            "fields": "files(id, name, mimeType, modifiedTime, size, webViewLink, iconLink)",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        if shared_drive_id:
            params["driveId"] = shared_drive_id
            params["corpora"] = "drive"
        else:
            params["corpora"] = "user"

        results = self.service.files().list(**params).execute()
        return results.get("files", [])

    def read_file_content(self, file_id: str) -> dict[str, Any]:
        meta = self.service.files().get(fileId=file_id, fields="mimeType, name").execute()
        mime_type = meta.get("mimeType")

        if mime_type.startswith("application/vnd.google-apps."):
            return self._export_google_file(file_id, mime_type)
        return self._download_regular_file(file_id, mime_type)

    def create_folder(self, folder_name: str, parent_folder_id: str | None = None, shared_drive_id: str | None = None) -> dict:
        metadata = {"name": folder_name.strip(), "mimeType": "application/vnd.google-apps.folder"}
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]
        elif shared_drive_id:
            metadata["parents"] = [shared_drive_id]

        return self.service.files().create(
            body=metadata,
            fields="id, name, parents, webViewLink, createdTime",
            supportsAllDrives=True,
        ).execute()

    def upload_file(self, filename: str, content_base64: str, parent_folder_id: str | None = None, shared_drive_id: str | None = None) -> dict:
        content_bytes = base64.b64decode(content_base64, validate=True)
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type is None:
            mime_type = "application/octet-stream"

        metadata = {"name": filename}
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]
        elif shared_drive_id:
            metadata["parents"] = [shared_drive_id]

        media = MediaIoBaseUpload(io.BytesIO(content_bytes), mimetype=mime_type)
        return self.service.files().create(
            body=metadata, media_body=media,
            fields="id,name,mimeType,modifiedTime,size,webViewLink",
            supportsAllDrives=True,
        ).execute()

    def delete_file(self, file_id: str) -> dict:
        self.service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        return {"success": True}

    def list_shared_drives(self, page_size: int = 100) -> list[dict]:
        results = self.service.drives().list(
            pageSize=min(max(1, page_size), 100),
            fields="drives(id, name)",
        ).execute()
        return results.get("drives", [])

    def _export_google_file(self, file_id: str, mime_type: str) -> dict:
        export_map = {
            "application/vnd.google-apps.document": "text/markdown",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
            "application/vnd.google-apps.drawing": "image/png",
        }
        export_mime = export_map.get(mime_type)
        if not export_mime:
            return {"error": True, "message": f"Unsupported type: {mime_type}"}

        request = self.service.files().export_media(fileId=file_id, mimeType=export_mime)
        content = self._download(request)

        if export_mime.startswith("text/"):
            return {"mimeType": export_mime, "content": content.decode("utf-8"), "encoding": "utf-8"}
        return {"mimeType": export_mime, "content": base64.b64encode(content).decode(), "encoding": "base64"}

    def _download_regular_file(self, file_id: str, mime_type: str) -> dict:
        request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
        content = self._download(request)

        if mime_type.startswith("text/") or mime_type == "application/json":
            return {"mimeType": mime_type, "content": content.decode("utf-8"), "encoding": "utf-8"}
        return {"mimeType": mime_type, "content": base64.b64encode(content).decode(), "encoding": "base64"}

    def _download(self, request) -> bytes:
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return fh.getvalue()
