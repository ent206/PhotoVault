import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.models import FileRecord, TransferSession, TransferStatus


class SessionLog:
    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = Path(log_dir) if log_dir else Path("session_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.log_dir / f"{session_id}.json"

    def save(self, session: TransferSession) -> None:
        self._path(session.session_id).write_text(
            json.dumps(self._serialize(session), indent=2)
        )

    def load(self, session_id: str) -> TransferSession:
        data = json.loads(self._path(session_id).read_text())
        return self._deserialize(data)

    def update_file(
        self,
        session_id: str,
        filename: str,
        status: TransferStatus,
        checksum: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        session = self.load(session_id)
        for f in session.files:
            if f.filename == filename:
                f.status = status
                f.transferred_at = datetime.now()
                if checksum is not None:
                    f.checksum = checksum
                if error is not None:
                    f.error = error
                break
        self.save(session)

    def find_incomplete(self) -> List[TransferSession]:
        result = []
        for p in self.log_dir.glob("*.json"):
            try:
                session = self.load(p.stem)
                if not session.is_complete:
                    result.append(session)
            except Exception:
                pass
        return sorted(result, key=lambda s: s.started_at, reverse=True)

    def _serialize(self, session: TransferSession) -> dict:
        return {
            "session_id": session.session_id,
            "started_at": session.started_at.isoformat(),
            "source_device": session.source_device,
            "destination_path": session.destination_path,
            "total_files": session.total_files,
            "files": [
                {
                    "filename": f.filename,
                    "source_path": f.source_path,
                    "destination_path": f.destination_path,
                    "file_size": f.file_size,
                    "status": f.status.value,
                    "checksum": f.checksum,
                    "transferred_at": f.transferred_at.isoformat() if f.transferred_at else None,
                    "error": f.error,
                }
                for f in session.files
            ],
        }

    def _deserialize(self, data: dict) -> TransferSession:
        files = [
            FileRecord(
                filename=f["filename"],
                source_path=f["source_path"],
                destination_path=f["destination_path"],
                file_size=f["file_size"],
                status=TransferStatus(f["status"]),
                checksum=f.get("checksum"),
                transferred_at=datetime.fromisoformat(f["transferred_at"]) if f.get("transferred_at") else None,
                error=f.get("error"),
            )
            for f in data["files"]
        ]
        return TransferSession(
            session_id=data["session_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            source_device=data["source_device"],
            destination_path=data["destination_path"],
            total_files=data["total_files"],
            files=files,
        )
