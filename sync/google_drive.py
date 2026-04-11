from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, Iterable

from v2.config import settings_v2


def sync_outputs_local_gdrive(paths: Iterable[Path]) -> Dict[str, str]:
    """
    If GDRIVE_PATH is mounted (e.g., Google Drive desktop mount), copy files there.
    """
    out: Dict[str, str] = {}
    gpath = settings_v2.gdrive_path.strip()
    if not gpath:
        return out

    dst_root = Path(gpath)
    if not dst_root.exists():
        return out

    for p in paths:
        if not p.exists():
            continue
        dst = dst_root / p.name
        shutil.copy2(p, dst)
        out[str(p)] = str(dst)
    return out


def upload_with_service_account(paths: Iterable[Path]) -> Dict[str, str]:
    """
    Optional native Drive upload via service account.
    Requires GOOGLE_SERVICE_ACCOUNT_JSON + GOOGLE_DRIVE_FOLDER_ID.
    """
    uploaded: Dict[str, str] = {}
    if not settings_v2.service_account_json or not settings_v2.gdrive_folder_id:
        return uploaded

    try:
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.http import MediaFileUpload  # type: ignore
    except Exception:
        return uploaded

    creds_info = json.loads(settings_v2.service_account_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )

    service = build("drive", "v3", credentials=creds)

    for p in paths:
        if not p.exists():
            continue
        file_metadata = {"name": p.name, "parents": [settings_v2.gdrive_folder_id]}
        media = MediaFileUpload(str(p), resumable=True)
        f = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        uploaded[str(p)] = f.get("id", "")

    return uploaded
