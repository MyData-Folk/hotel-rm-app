import os
import json
import shutil
from io import BytesIO
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

# PDF (reportlab)
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

# PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor

APP_VERSION = "9.1"
APP_NAME = "Hotel RM API"

# ──────────────────────────────────────────────────────────────────────────────
# Configuration & helpers
# ──────────────────────────────────────────────────────────────────────────────
UPLOAD_ROOT = os.getenv("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

# DB via DATABASE_URL (recommandé) ou variables séparées
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    pg_user = os.getenv("POSTGRES_USER", "postgres")
    pg_password = os.getenv("POSTGRES_PASSWORD", "postgres")
    pg_db = os.getenv("POSTGRES_DB", "postgres")
    pg_host = os.getenv("POSTGRES_HOST", "hotel-db")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    DATABASE_URL = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"

def db_conn():
    return psycopg2.connect(DATABASE_URL)

def ensure_schema():
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hotel_files (
                    id BIGSERIAL PRIMARY KEY,
                    hotel_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    kind TEXT CHECK (kind IN ('upload','export')) NOT NULL,
                    format TEXT,               -- 'excel' | 'pdf' | 'json' | 'xlsx' etc.
                    path TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS hotel_files_hotelid_created_idx ON hotel_files(hotel_id, created_at DESC);")
        conn.commit()

def hotel_paths(hotel_id: str) -> Dict[str, str]:
    """Retourne les chemins (uploads/exports/logs) pour un hôtel et l'année courante, créés si nécessaire."""
    year = datetime.now().year
    base = os.path.join(UPLOAD_ROOT, f"{hotel_id}_{year}")
    paths = {
        "base": base,
        "uploads": os.path.join(base, "uploads"),
        "exports": os.path.join(base, "exports"),
        "logs": os.path.join(base, "logs"),
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    return paths

def register_file(hotel_id: str, kind: str, fmt: str, filename: str, path: str) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO hotel_files (hotel_id, filename, kind, format, path) VALUES (%s,%s,%s,%s,%s);",
                (hotel_id, filename, kind, fmt, path)
            )
        conn.commit()

def prune_old(hotel_id: str, kind: str, keep: int = 10) -> None:
    """Conserve uniquement les 'keep' plus récents pour (hotel_id, kind). Supprime le reste disque+DB."""
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, path FROM hotel_files
                WHERE hotel_id=%s AND kind=%s
                ORDER BY created_at DESC
                OFFSET %s
            """, (hotel_id, kind, keep))
            old = cur.fetchall() or []
            if not old:
                return
            # delete physical files then db rows
            for row in old:
                try:
                    if row["path"] and os.path.exists(row["path"]):
                        os.remove(row["path"])
                except Exception:
                    pass
            cur.execute("""
                DELETE FROM hotel_files
                WHERE id = ANY(%s)
            """, ([r["id"] for r in old],))
        conn.commit()

def list_last_files(hotel_id: str, kinds: Optional[List[str]]=None, limit:int=10) -> List[Dict[str, Any]]:
    kinds = kinds or ["upload", "export"]
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""
                SELECT id, hotel_id, filename, kind, format, path, created_at
                FROM hotel_files
                WHERE hotel_id=%s AND kind = ANY(%s)
                ORDER BY created_at DESC
                LIMIT %s
            """, (hotel_id, kinds, limit))
            rows = cur.fetchall() or []
            return [
                {
                    "id": r["id"],
                    "hotel_id": r["hotel_id"],
                    "filename": r["filename"],
                    "kind": r["kind"],
                    "format": r.get("format"),
                    "path": r["path"],
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None
                } for r in rows
            ]

def bytes_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except Exception:
        return 0

def folder_size_bytes(folder: str) -> int:
    total = 0
    for root, _, files in os.walk(folder):
        for f in files:
            total += bytes_size(os.path.join(root, f))
    return total

# ──────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(title=APP_NAME, version=APP_VERSION, description="API RM multi-tenant (uploads + exports + historique)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://admin-folkestone.e-hotelmanager.com",
        "https://folkestone.e-hotelmanager.com",
        "http://localhost:5500",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    ensure_schema()
    os.makedirs(UPLOAD_ROOT, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Health & Monitor
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "time": datetime.utcnow().isoformat() + "Z"
    }

@app.get("/monitor")
def monitor():
    # Compteurs par DB + taille disque
    hotels = set()
    uploads_count = 0
    exports_count = 0
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM hotel_files WHERE kind='upload';")
            uploads_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM hotel_files WHERE kind='export';")
            exports_count = cur.fetchone()[0]
            cur.execute("SELECT DISTINCT hotel_id FROM hotel_files;")
            hotels = {r[0] for r in cur.fetchall()}

    disk_mb = round(folder_size_bytes(UPLOAD_ROOT) / 1_000_000, 2)
    return {
        "status": "running",
        "hotels_tracked": len(hotels),
        "uploads": uploads_count,
        "exports": exports_count,
        "storage_mb": disk_mb,
    }

# ──────────────────────────────────────────────────────────────────────────────
# Uploads
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/upload/excel")
async def upload_excel(hotel_id: str = Query(...), file: UploadFile = File(...)):
    if not hotel_id:
        raise HTTPException(status_code=400, detail="hotel_id requis")

    paths = hotel_paths(hotel_id)
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ext = os.path.splitext(file.filename)[1] or ".xlsx"
    safe_name = f"{date_str}_{file.filename}".replace(" ", "_")
    target = os.path.join(paths["uploads"], safe_name)

    try:
        with open(target, "wb") as f:
            shutil.copyfileobj(file.file, f)
        register_file(hotel_id, kind="upload", fmt=ext.lstrip(".").lower(), filename=safe_name, path=target)
        prune_old(hotel_id, kind="upload", keep=10)
        return {"status": "ok", "message": f"Fichier sauvegardé: {safe_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload échoué: {e}")

@app.post("/upload/json")
async def upload_json(hotel_id: str = Query(...), file: UploadFile = File(...)):
    if not hotel_id:
        raise HTTPException(status_code=400, detail="hotel_id requis")

    paths = hotel_paths(hotel_id)
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ext = os.path.splitext(file.filename)[1] or ".json"
    safe_name = f"{date_str}_{file.filename}".replace(" ", "_")
    target = os.path.join(paths["uploads"], safe_name)

    try:
        with open(target, "wb") as f:
            shutil.copyfileobj(file.file, f)
        register_file(hotel_id, kind="upload", fmt=ext.lstrip(".").lower(), filename=safe_name, path=target)
        prune_old(hotel_id, kind="upload", keep=10)
        return {"status": "ok", "message": f"Fichier JSON sauvegardé: {safe_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload échoué: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Historique (10 derniers)
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/files/status")
def files_status(hotel_id: str = Query(...)):
    if not hotel_id:
        raise HTTPException(status_code=400, detail="hotel_id requis")
    rows = list_last_files(hotel_id, kinds=["upload", "export"], limit=10)
    # enrichir avec taille (optionnel)
    for r in rows:
        r["size_bytes"] = bytes_size(r["path"]) if r.get("path") else None
    return {"hotel_id": hotel_id, "files": rows}

# ──────────────────────────────────────────────────────────────────────────────
# Export Excel / PDF
# ──────────────────────────────────────────────────────────────────────────────
def normalize_tabular(rows: Any, columns: Optional[List[str]] = None) -> Tuple[List[str], List[List[Any]]]:
    if not rows:
        return (columns or [], [])
    if isinstance(rows[0], dict):
        keys = columns or list(rows[0].keys())
        data = [[r.get(k) for k in keys] for r in rows]
        return (keys, data)
    if isinstance(rows[0], (list, tuple)):
        if columns is None:
            max_len = max(len(r) for r in rows)
            columns = [f"col_{i+1}" for i in range(max_len)]
        return (columns, [list(r) for r in rows])
    return (columns or ["value"], [[str(x)] for x in rows])

@app.post("/export/excel")
def export_excel(
    payload: Dict[str, Any] = Body(..., example={
        "kind": "reservations",         # ou "disponibilites"
        "hotel_id": "folkestone",
        "columns": ["date","room","price","status"],
        "rows": [
            ["2025-10-21","101",150,"booked"],
            ["2025-10-22","102",130,"available"]
        ],
        "metadata": {"source":"admin"}
    })
):
    kind = (payload.get("kind") or "reservations").lower()
    hotel_id = payload.get("hotel_id") or "unknown"
    rows = payload.get("rows") or payload.get("data") or []
    columns = payload.get("columns")
    metadata = payload.get("metadata") or {}

    if not hotel_id:
        raise HTTPException(status_code=400, detail="hotel_id requis")

    headers, data = normalize_tabular(rows, columns)
    df = pd.DataFrame(data, columns=headers or None)

    paths = hotel_paths(hotel_id)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{kind}_{hotel_id}_{ts}.xlsx"
    out_path = os.path.join(paths["exports"], filename)

    try:
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            sheet = ("reservations" if kind.startswith("reserv") else "disponibilites").capitalize()
            df.to_excel(writer, index=False, sheet_name=sheet)
            # onglet Meta
            wb = writer.book
            meta_ws = wb.create_sheet("Meta")
            meta_ws.append(["hotel_id", hotel_id])
            meta_ws.append(["kind", kind])
            meta_ws.append(["generated_at", datetime.utcnow().isoformat() + "Z"])
            for k, v in metadata.items():
                meta_ws.append([k, str(v)])

        register_file(hotel_id, kind="export", fmt="xlsx", filename=filename, path=out_path)
        prune_old(hotel_id, kind="export", keep=10)
        return FileResponse(out_path,
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            filename=filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export Excel échoué: {e}")

@app.post("/export/pdf")
def export_pdf(
    payload: Dict[str, Any] = Body(..., example={
        "kind": "disponibilites",       # ou "reservations"
        "hotel_id": "folkestone",
        "columns": ["date","rooms_available","occ_rate"],
        "rows": [
            ["2025-10-21", 20, 0.85],
            ["2025-10-22", 18, 0.88]
        ],
        "metadata": {"source":"admin"}
    })
):
    kind = (payload.get("kind") or "reservations").lower()
    hotel_id = payload.get("hotel_id") or "unknown"
    rows = payload.get("rows") or payload.get("data") or []
    columns = payload.get("columns")
    metadata = payload.get("metadata") or {}

    if not hotel_id:
        raise HTTPException(status_code=400, detail="hotel_id requis")

    headers, data = normalize_tabular(rows, columns)
    table_data = [headers] + data if headers else data

    paths = hotel_paths(hotel_id)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{kind}_{hotel_id}_{ts}.pdf"
    out_path = os.path.join(paths["exports"], filename)

    try:
        doc = SimpleDocTemplate(out_path, pagesize=landscape(A4), title=f"{kind} - {hotel_id}")
        styles = getSampleStyleSheet()
        story = []
        story.append(Paragraph(f"{kind.capitalize()} — Hôtel: {hotel_id}", styles["Title"]))
        story.append(Spacer(1, 12))
        meta_text = ", ".join([f"{k}: {v}" for k, v in metadata.items()]) if metadata else "—"
        story.append(Paragraph(f"<b>Méta:</b> {meta_text}", styles["Normal"]))
        story.append(Spacer(1, 10))

        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e5e7eb')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#111827')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f9fafb')]),
        ]))
        story.append(table)
        doc.build(story)

        register_file(hotel_id, kind="export", fmt="pdf", filename=filename, path=out_path)
        prune_old(hotel_id, kind="export", keep=10)
        return FileResponse(out_path, media_type="application/pdf", filename=filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export PDF échoué: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Lancement local
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
