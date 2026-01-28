import os
import pickle
import importlib
from typing import Any


class GoogleDriveIntegration:
    SCOPES = ["https://www.googleapis.com/auth/drive.file"]

    def __init__(self, credentials_path="credentials.json", token_path="token.pickle"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service: Any = None

    def _load_dependencies(self):
        google_auth_oauthlib = importlib.import_module("google_auth_oauthlib.flow")
        google_api_client = importlib.import_module("googleapiclient.discovery")
        google_media = importlib.import_module("googleapiclient.http")
        google_credentials = importlib.import_module("google.oauth2.credentials")
        google_requests = importlib.import_module("google.auth.transport.requests")

        return {
            "InstalledAppFlow": google_auth_oauthlib.InstalledAppFlow,
            "build": google_api_client.build,
            "MediaFileUpload": google_media.MediaFileUpload,
            "Credentials": google_credentials.Credentials,
            "Request": google_requests.Request,
        }

    def authenticate(self):
        deps = self._load_dependencies()
        creds = None

        if os.path.exists(self.token_path):
            with open(self.token_path, "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(deps["Request"]())
            else:
                flow = deps["InstalledAppFlow"].from_client_secrets_file(
                    self.credentials_path,
                    self.SCOPES,
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_path, "wb") as token:
                pickle.dump(creds, token)

        self.service = deps["build"]("drive", "v3", credentials=creds)
        return True

    def _ensure_service(self):
        if self.service is None:
            raise RuntimeError("Google Drive not authenticated")

    def list_folders(self, parent_id="root"):
        self._ensure_service()
        results = self.service.files().list(
            q=(
                f"'{parent_id}' in parents "
                "and mimeType='application/vnd.google-apps.folder'"
            ),
            spaces="drive",
            fields="files(id, name)",
        ).execute()
        return results.get("files", [])

    def create_folder(self, name, parent_id="root"):
        self._ensure_service()
        file_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = self.service.files().create(body=file_metadata, fields="id").execute()
        return folder.get("id")

    def upload_file(self, filepath, folder_id="root", filename=None):
        self._ensure_service()
        deps = self._load_dependencies()
        if filename is None:
            filename = os.path.basename(filepath)

        mime_types = {
            ".txt": "text/plain",
            ".srt": "application/x-subrip",
            ".vtt": "text/vtt",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pdf": "application/pdf",
        }
        ext = os.path.splitext(filepath)[1].lower()
        mime_type = mime_types.get(ext, "application/octet-stream")

        file_metadata = {
            "name": filename,
            "parents": [folder_id],
        }

        media = deps["MediaFileUpload"](filepath, mimetype=mime_type)
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
        ).execute()
        return {
            "id": file.get("id"),
            "link": file.get("webViewLink"),
        }
