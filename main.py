import os
import json
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from typing import List
from datetime import datetime

# Librairies export Excel / PDF
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ───────────────────────────────────────────────
# Initialisation de l'application
# ───────────────────────────────────────────────
app = FastAPI(
    title="Hotel RM App API",
    description="API centrale Folkestone RM : gestion des uploads, configs, data, monitoring et exports.",
    version="8.0"
)

# ───────────────────────────────────────────────
# CORS - autoriser frontends admin & public
# ───────────────────────────────────────────────
origins = [
    "https://admin-folkestone.e-hotelmanager.com",
    "https://folkestone.e-hotelmanager.com",
    "http://localhost:5500"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ───────────────────────────────────────────────
# Chemins et variables globales
# ───────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR, exist_ok=True)

DATA_CONFIG_FILE = os.path.join(BASE_DIR, "data_config.json")

# ───────────────────────────────────────────────
# ROUTE DE SANTÉ
# ───────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "healthy",
        "version": "8.0",
        "cors": "enabled"
    }

# ───────────────────────────────────────────────
# ROUTES ADMIN - LISTE DES HÔTELS
# ───────────────────────────────────────────────
@app.get("/hotels")
def get_hotels():
    try:
        if os.path.exists(DATA_CONFIG_FILE):
            with open(DATA_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("hotels", [])
        else:
            return [
                {"id": "folkestone", "name": "Folkestone Opera"},
                {"id": "washington", "name": "Washington Opera"},
                {"id": "vendome_opera", "name": "Vendome Opera"},
                {"id": "grand_hotel_du_havre", "name": "Grand Hôtel du Havre"},
                {"id": "hotel_opal", "name": "Hôtel Opal"},
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ───────────────────────────────────────────────
# ROUTE : Upload de fichier Excel ou JSON
# ───────────────────────────────────────────────
@app.post("/upload/excel")
async def upload_excel(hotel_id: str = Query(...), file: UploadFile = File(...)):
    try:
        hotel_folder = os.path.join(UPLOAD_DIR, hotel_id)
        os.makedirs(hotel_folder, exist_ok=True)

        file_path = os.path.join(hotel_folder, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())

        return {"status": "success", "message": f"Fichier {file.filename} enregistré pour {hotel_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload/json")
async def upload_json(hotel_id: str = Query(...), file: UploadFile = File(...)):
    try:
        hotel_folder = os.path.join(UPLOAD_DIR, hotel_id)
        os.makedirs(hotel_folder, exist_ok=True)
        file_path = os.path.join(hotel_folder, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        return {"status": "success", "message": f"JSON {file.filename} enregistré pour {hotel_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ───────────────────────────────────────────────
# ROUTE : Statut des fichiers uploadés
# ───────────────────────────────────────────────
@app.get("/files/status")
def file_status(hotel_id: str):
    hotel_folder = os.path.join(UPLOAD_DIR, hotel_id)
    if not os.path.exists(hotel_folder):
        return {"status": "empty", "files": []}
    files = [
        {"name": f, "size": os.path.getsize(os.path.join(hotel_folder, f))}
        for f in os.listdir(hotel_folder)
    ]
    return {"status": "ok", "files": files}

# ───────────────────────────────────────────────
# ROUTE : Config / Data pour la simulation
# ───────────────────────────────────────────────
@app.get("/config")
def get_config(hotel_id: str):
    config_path = os.path.join(UPLOAD_DIR, hotel_id, "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        raise HTTPException(status_code=404, detail="Configuration introuvable")

@app.get("/data")
def get_data(hotel_id: str):
    folder = os.path.join(UPLOAD_DIR, hotel_id)
    if not os.path.exists(folder):
        raise HTTPException(status_code=404, detail="Dossier non trouvé")
    excel_files = [f for f in os.listdir(folder) if f.endswith(".xlsx")]
    if not excel_files:
        raise HTTPException(status_code=404, detail="Aucun fichier Excel trouvé")
    return {"status": "ok", "files": excel_files}

# ───────────────────────────────────────────────
# EXPORT EXCEL / PDF
# ───────────────────────────────────────────────
@app.post("/export/excel")
def export_excel(data: List[dict]):
    try:
        df = pd.DataFrame(data)
        output = BytesIO()
        df.to_excel(output, index=False, sheet_name="Simulation")
        output.seek(0)
        return FileResponse(
            path_or_file=output,
            filename=f"simulation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/export/pdf")
def export_pdf(data: List[dict]):
    try:
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        pdf.drawString(100, 800, "Simulation Tarifs Hôtel")
        y = 750
        for row in data:
            pdf.drawString(100, y, str(row))
            y -= 20
            if y < 50:
                pdf.showPage()
                y = 800
        pdf.save()
        buffer.seek(0)
        return FileResponse(
            path_or_file=buffer,
            filename=f"simulation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            media_type="application/pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ───────────────────────────────────────────────
# MONITORING BASIQUE
# ───────────────────────────────────────────────
@app.get("/monitor")
def monitor_status():
    try:
        total_hotels = len(os.listdir(UPLOAD_DIR))
        total_files = sum(len(files) for _, _, files in os.walk(UPLOAD_DIR))
        disk_usage = round(sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, filenames in os.walk(UPLOAD_DIR) for f in filenames) / 1_000_000, 2)
        return {
            "status": "running",
            "hotels": total_hotels,
            "files": total_files,
            "storage_mb": disk_usage
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ───────────────────────────────────────────────
# MAIN
# ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
