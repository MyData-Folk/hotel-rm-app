import os
import io
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# === Directories & env ===
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
BACKUP_DIR = os.getenv("BACKUP_DIR", "/app/backups")
LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
for d in (DATA_DIR, BACKUP_DIR, LOG_DIR):
    os.makedirs(d, exist_ok=True)

# === App init ===
app = FastAPI(title="Hotel RM App", version="monitor-optimized")

# CORS: allow all subdomains of e-hotelmanager.com
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://([a-z0-9-]+\.)*e-hotelmanager\.com|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static mounts for logs and backups
app.mount("/logs", StaticFiles(directory=LOG_DIR), name="logs")
app.mount("/backups", StaticFiles(directory=BACKUP_DIR), name="backups")

# Logging to file + console
logger = logging.getLogger("hotel-rm")
logger.setLevel(logging.INFO)
if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
    fh = logging.FileHandler(os.path.join(LOG_DIR, "app.log"))
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)

# === Mock hotel data (replace with DB later) ===
HOTELS = ["folkestone","washington","vendome opera","grand_hotel_du_havre","hotel opal","hotel du test"]

@app.get("/", tags=["Status"])
def root():
    return {"status":"ok","time": datetime.utcnow().isoformat()}

@app.get("/health", tags=["Status"])
def health():
    return {"status":"ok","time": datetime.utcnow().isoformat()}

@app.get("/hotels", tags=["Hotel Management"], response_model=List[str])
def list_hotels():
    logger.info("Liste des hôtels récupérée: %d hôtels", len(HOTELS))
    return HOTELS

# ---- Export Excel ----
@app.post("/export/excel", tags=["Export"])
def export_excel(data: Dict[str, Any] = Body(..., description="Simulation output to export")):
    # Expect 'rows' key as list of dicts or 'data' key with list of rows
    rows = data.get("rows") or data.get("data") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="No data provided for Excel export")
    df = pd.DataFrame(rows)

    # Create Excel in memory
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Données", index=False)
        # Optional: write a summary sheet if provided
        summary = data.get("summary")
        if isinstance(summary, dict) and summary:
            sdf = pd.DataFrame([{k: summary[k] for k in summary}])
            sdf.to_excel(writer, sheet_name="Résumé", index=False)
    buf.seek(0)

    # Also save under DATA_DIR for persistence with timestamp
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_path = os.path.join(DATA_DIR, f"export-{ts}.xlsx")
    with open(out_path, "wb") as f:
        f.write(buf.getbuffer())

    headers = {
        "Content-Disposition": f'attachment; filename="export-{ts}.xlsx"'
    }
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)

# ---- Export PDF (simple, pure-Python using reportlab) ----
@app.post("/export/pdf", tags=["Export"])
def export_pdf(data: Dict[str, Any] = Body(...)):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ReportLab not available: {e}")

    rows = data.get("rows") or data.get("data") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="No data provided for PDF export")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    title = data.get("title") or "Rapport Simulation"
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, height-2*cm, title)
    c.setFont("Helvetica", 10)
    c.drawString(2*cm, height-2.6*cm, datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))

    # Table-like rendering
    y = height - 3.2*cm
    max_cols = 6
    # Determine columns
    cols = list(rows[0].keys())[:max_cols]
    col_w = (width - 4*cm) / len(cols)

    # Header
    c.setFont("Helvetica-Bold", 9)
    for i, col in enumerate(cols):
        c.drawString(2*cm + i*col_w, y, str(col)[:20])
    y -= 0.6*cm
    c.setFont("Helvetica", 9)

    for r in rows[:40]:  # limit rows per page for simplicity
        if y < 2*cm:
            c.showPage()
            y = height - 2*cm
        for i, col in enumerate(cols):
            val = r.get(col, "")
            c.drawString(2*cm + i*col_w, y, str(val)[:25])
        y -= 0.5*cm

    c.showPage()
    c.save()
    buf.seek(0)

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_path = os.path.join(DATA_DIR, f"export-{ts}.pdf")
    with open(out_path, "wb") as f:
        f.write(buf.getbuffer())

    headers = {"Content-Disposition": f'attachment; filename="export-{ts}.pdf"'}
    return StreamingResponse(buf, media_type="application/pdf", headers=headers)

# ---- Files status (example placeholder, keep compatibility) ----
@app.get("/files/status", tags=["Files"])
def files_status(hotel_id: str = Query(...)):
    data_path = os.path.join(DATA_DIR, f"{hotel_id}_tarifs.xlsx")
    config_exists = os.path.exists(os.path.join(DATA_DIR, f"{hotel_id}_config.json"))
    return {
        "hotel_id": hotel_id,
        "data_file_exists": os.path.exists(data_path),
        "config_exists": config_exists,
        "checked": datetime.utcnow().isoformat()
    }

# Include routers
from admin_endpoints import router as admin_router
from routes_monitoring import router as monitor_router
app.include_router(admin_router)
app.include_router(monitor_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
