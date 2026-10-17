from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "text/csv": ".csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "video/mp4": ".mp4",
    "text/plain": ".txt",
}


@dataclass
class SavedUpload:
    original_name: str
    path: Path
    media_type: str
    sha256: str
    size: int


def _sniff_type(data: bytes, declared: str | None, name: str) -> str:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) > 12 and data[4:8] == b"ftyp":
        return "video/mp4"
    if data.startswith(b"PK\x03\x04") and name.lower().endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if declared in {"text/csv", "text/plain"}:
        try:
            data[:4096].decode("utf-8")
            return declared
        except UnicodeDecodeError as exc:
            raise HTTPException(415, "Text upload must be UTF-8") from exc
    raise HTTPException(415, "Unsupported or mismatched file content")


async def save_upload(upload: UploadFile, root: Path, max_bytes: int) -> SavedUpload:
    raw_name = Path(upload.filename or "upload").name
    if raw_name != (upload.filename or "upload") or ".." in raw_name:
        raise HTTPException(400, "Unsafe filename")
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name)[:120]
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, "Upload exceeds configured size limit")
    if not data:
        raise HTTPException(400, "Empty upload")
    media_type = _sniff_type(data, upload.content_type, safe_name)
    if media_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Unsupported file type")
    digest = hashlib.sha256(data).hexdigest()
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / f"{digest[:16]}-{safe_name}").resolve()
    if root not in target.parents:
        raise HTTPException(400, "Unsafe storage path")
    if not target.exists():
        target.write_bytes(data)
    return SavedUpload(raw_name, target, media_type, digest, len(data))

