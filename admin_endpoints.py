import os
import subprocess
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from typing import Optional

router = APIRouter(prefix="/admin", tags=["Admin"])

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
ENV = os.getenv("ENV", "dev")
if not ADMIN_TOKEN:
    if ENV == "dev":
        ADMIN_TOKEN = "dev-admin-token"
    else:
        raise RuntimeError("ADMIN_TOKEN must be provided via environment variables to protect admin endpoints")

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
BACKUP_DIR = os.getenv("BACKUP_DIR", "/app/backups")
LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

def require_admin_token(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return True

@router.post("/backup")
def backup_database(authorized: bool = Depends(require_admin_token)):
    db_url = os.getenv("DATABASE_URL") or os.getenv("DB_URL")
    if not db_url:
        raise HTTPException(status_code=400, detail="DATABASE_URL is not configured")

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    outfile = os.path.join(BACKUP_DIR, f"backup-{ts}.sql")
    try:
        # Use pg_dump from postgresql-client
        subprocess.run(["pg_dump", db_url, "-f", outfile], check=True)
        rel = f"/backups/{os.path.basename(outfile)}"
        return {"status": "ok", "path": rel, "created_at": ts}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"pg_dump failed: {e}")
