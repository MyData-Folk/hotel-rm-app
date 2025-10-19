from fastapi import APIRouter
import os
import shutil
import time

router = APIRouter(prefix="/monitor")


@router.get("/health")
def system_health():
    db_ok = os.path.exists("/app/data")
    supabase_ok = True  # à tester via ping si possible
    total, used, free = shutil.disk_usage("/app")
    return {
        "api": "ok",
        "db_mount": db_ok,
        "supabase": supabase_ok,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "disk": {
            "total": total,
            "used": used,
            "free": free,
        },
    }


@router.get("/files")
def list_uploaded_files():
    dir_path = "/app/data"
    if not os.path.exists(dir_path):
        return {"files": []}

    files = []
    for filename in os.listdir(dir_path):
        full_path = os.path.join(dir_path, filename)
        try:
            size = os.path.getsize(full_path)
            modified = time.ctime(os.path.getmtime(full_path))
        except OSError:
            size = 0
            modified = None
        files.append({
            "name": filename,
            "size": size,
            "modified": modified,
        })
    return {"files": files}
