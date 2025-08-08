# backend/services/deliverable_service.py
import os
from datetime import datetime
from backend.db import get_session
from backend.models import Deliverable

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "storage")

def save_deliverable(user_id: int, kind: str, data: dict, title: str | None = None, file_path: str | None = None, project_id: int | None = None):
    with get_session() as s:
        d = Deliverable(
            user_id=user_id,
            project_id=project_id,
            kind=kind,
            title=title,
            json_content=data or {},
            file_path=file_path
        )
        s.add(d)
        s.commit()
        s.refresh(d)
        return d.id

def write_landing_file(user_id: int, html: str) -> str:
    # Ex: backend/storage/landings/<user_id>/landing-<timestamp>.html
    folder = os.path.join(STORAGE_DIR, "landings", str(user_id))
    os.makedirs(folder, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(folder, f"landing-{ts}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path