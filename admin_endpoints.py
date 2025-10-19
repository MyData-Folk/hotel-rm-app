import os
import subprocess
import psycopg2
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from datetime import datetime
from pathlib import Path

router = APIRouter(prefix="/admin", tags=["Admin Tools"])

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "superadmintoken")  # 👈 change-le dans Coolify
BACKUP_DIR = Path("/app/backups")
LOG_PATH = Path("/app/logs/app.log")
DB_URL = os.getenv("DATABASE_URL", "postgres://postgres:supersecretpassword@hotel-db:5432/hoteldb")

# --- Helper de sécurité
def require_admin(token: str):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

# --- 1️⃣ Sauvegarde PostgreSQL
@router.post("/backup")
def backup_database(x_admin_token: str = Header(None)):
    require_admin(x_admin_token)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_file = BACKUP_DIR / f"hoteldb_{timestamp}.sql"

    try:
        cmd = [
            "pg_dump", DB_URL,
            "-f", str(backup_file)
        ]
        subprocess.run(cmd, check=True)
        return {"status": "ok", "url": f"/backups/{backup_file.name}"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}")

# --- 2️⃣ Liste des sauvegardes
@router.get("/backups")
def list_backups(x_admin_token: str = Header(None)):
    require_admin(x_admin_token)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted([f"/backups/{p.name}" for p in BACKUP_DIR.glob("*.sql")], reverse=True)
    return {"files": files, "count": len(files)}

# --- 3️⃣ Logs
@router.get("/logs")
def get_logs(lines: int = 200, x_admin_token: str = Header(None)):
    require_admin(x_admin_token)
    if not LOG_PATH.exists():
        return {"message": f"Log file {LOG_PATH} not found."}
    with open(LOG_PATH, "r") as f:
        content = f.readlines()[-lines:]
    return JSONResponse(content={"logs": content})

# --- 4️⃣ SQL (readonly)
@router.post("/sql")
def run_sql(request: Request, x_admin_token: str = Header(None)):
    require_admin(x_admin_token)
    body = request.json()
    sql = body.get("sql", "")
    readonly = body.get("readonly", True)
    if not sql:
        raise HTTPException(status_code=400, detail="SQL query required")

    # sécurité minimale
    if not readonly and any(w in sql.lower() for w in ["delete", "update", "drop", "alter", "insert"]):
        raise HTTPException(status_code=403, detail="Write operations not allowed")

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()
        results = [dict(zip(columns, r)) for r in rows]
        return {"status": "ok", "count": len(results), "rows": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 5️⃣ Redeploy (optionnel, via Coolify API)
@router.post("/redeploy")
def trigger_redeploy(x_admin_token: str = Header(None)):
    require_admin(x_admin_token)
    COOLIFY_API = os.getenv("COOLIFY_API_URL")
    COOLIFY_TOKEN = os.getenv("COOLIFY_API_TOKEN")

    if not (COOLIFY_API and COOLIFY_TOKEN):
        return {"status": "error", "detail": "Coolify API credentials missing."}

    import requests
    r = requests.post(
        f"{COOLIFY_API}/deploy",
        headers={"Authorization": f"Bearer {COOLIFY_TOKEN}"},
    )
    return {"status": "ok" if r.ok else "error", "code": r.status_code}
