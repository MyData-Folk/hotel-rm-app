from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import os, time, shutil, socket

router = APIRouter(prefix="/monitor", tags=["Monitoring"])

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
BACKUP_DIR = os.getenv("BACKUP_DIR", "/app/backups")
LOG_DIR = os.getenv("LOG_DIR", "/app/logs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

@router.get("/health")
def system_health():
    # Disk usage
    total, used, free = shutil.disk_usage("/")
    # Basic checks
    checks = {
        "api": "ok",
        "data_dir_exists": os.path.exists(DATA_DIR),
        "backup_dir_exists": os.path.exists(BACKUP_DIR),
        "log_dir_exists": os.path.exists(LOG_DIR),
        "hostname": socket.gethostname(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "disk": {
            "total_gb": round(total/1e9, 2),
            "used_gb": round(used/1e9, 2),
            "free_gb": round(free/1e9, 2),
            "free_pct": round((free/total)*100, 2)
        }
    }
    return checks

@router.get("/files")
def list_data_files():
    files = []
    if os.path.isdir(DATA_DIR):
        for name in sorted(os.listdir(DATA_DIR)):
            p = os.path.join(DATA_DIR, name)
            if os.path.isfile(p):
                files.append({
                    "name": name,
                    "size_bytes": os.path.getsize(p),
                    "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p)))
                })
    return {"count": len(files), "files": files}

@router.get("/logs/tail")
def tail_logs(lines: int = 200):
    path = os.path.join(LOG_DIR, "app.log")
    if not os.path.exists(path):
        return {"lines": 0, "content": ""}
    try:
        with open(path, "rb") as f:
            data = f.read().splitlines()[-lines:]
        return JSONResponse({"lines": len(data), "content": [d.decode('utf-8', errors='ignore') for d in data]})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
