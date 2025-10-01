import os
import io
import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import SQLModel, Field, create_engine, Session, select

# --- 1. CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///local.db")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")

# Adapte l'URL pour psycopg2, le driver standard de PostgreSQL avec SQLAlchemy/SQLModel
engine = create_engine(DATABASE_URL.replace("postgres://", "postgresql+psycopg2://"), echo=False)

app = FastAPI(
    title="Hotel RM API - v6.2 (Stable & Robust)",
    description="API complète pour la gestion des données hôtelières et la simulation tarifaire."
)

# --- 2. MIDDLEWARE CORS ---
origins = [
    "https://folkestone.e-hotelmanager.com",
    "https://admin-folkestone.e-hotelmanager.com",
    # Ajouter les origines locales pour faciliter le développement
    "http://127.0.0.1:5500",
    "http://localhost:3000"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. MODÈLES DE DONNÉES (SQLMODEL & PYDANTIC) ---
class Hotel(SQLModel, table=True):
    hotel_id: str = Field(primary_key=True)

class HotelConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hotel_id: str = Field(index=True, unique=True)
    config_json: str

class SimulateIn(BaseModel):
    hotel_id: str
    room: str
    plan: str
    start: str
    end: str
    partner_name: Optional[str] = None

# --- 4. ÉVÉNEMENTS DE DÉMARRAGE DE L'APPLICATION ---
@app.on_event('startup')
def on_startup():
    SQLModel.metadata.create_all(engine)
    os.makedirs(DATA_DIR, exist_ok=True)

# --- 5. FONCTIONS DE PARSING AVANCÉES (CORRIGÉES) ---
def safe_int(val) -> int:
    """Tente de convertir une valeur en entier. Si échec (ex: contient 'X'), retourne 0."""
    if pd.isna(val): return 0
    try:
        return int(float(str(val).strip().replace(',', '.')))
    except (ValueError, TypeError):
        return 0

def parse_sheet_to_structure(df: pd.DataFrame) -> dict:
    hotel_data = {}
    if df.shape[0] < 1: return {}

    header_row = df.iloc[0].tolist()
    date_cols = []
    # Détection intelligente des colonnes de date
    for j, col_value in enumerate(header_row):
        if j < 3 or pd.isna(col_value): continue
        date_str = None
        try:
            if isinstance(col_value, (datetime, pd.Timestamp)):
                date_str = col_value.strftime('%Y-%m-%d')
            elif isinstance(col_value, (int, float)):
                date_str = (datetime(1899, 12, 30) + timedelta(days=col_value)).strftime('%Y-%m-%d')
            else:
                date_str = pd.to_datetime(str(col_value), dayfirst=True).strftime('%Y-%m-%d')
            if date_str: date_cols.append({'index': j, 'date': date_str})
        except Exception: continue

    current_room = None
    for i in range(1, df.shape[0]):
        row = df.iloc[i].tolist()
        if pd.notna(row[0]) and str(row[0]).strip(): current_room = str(row[0]).strip()
        if not current_room or len(row) < 3: continue
        descriptor = str(row[2]).strip().lower() if pd.notna(row[2]) else ""

        if 'left for sale' in descriptor:
            if current_room not in hotel_data: hotel_data[current_room] = {'stock': {}, 'plans': {}}
            for dc in date_cols:
                stock_value = row[dc['index']] if dc['index'] < len(row) else None
                hotel_data[current_room]['stock'][dc['date']] = safe_int(stock_value) # Utilisation de la fonction sécurisée
        
        elif 'price' in descriptor:
            plan_name = str(row[1]).strip() if pd.notna(row[1]) else "UNNAMED_PLAN"
            if current_room not in hotel_data: hotel_data[current_room] = {'stock': {}, 'plans': {}}
            if plan_name not in hotel_data[current_room]['plans']: hotel_data[current_room]['plans'][plan_name] = {}
            for dc in date_cols:
                price_value = row[dc['index']] if dc['index'] < len(row) else None
                try:
                    hotel_data[current_room]['plans'][plan_name][dc['date']] = float(str(price_value).replace(',', '.')) if pd.notna(price_value) else None
                except (ValueError, TypeError):
                    hotel_data[current_room]['plans'][plan_name][dc['date']] = None
                    
    return {'report_generated_at': str(datetime.now()), 'rooms': hotel_data}

# --- 6. ENDPOINTS DE L'API ---

@app.get("/", tags=["Status"])
def read_root(): return {"status": "Hotel RM API is running"}

# --- Gestion des Hôtels ---
@app.post("/hotels", tags=["Hotel Management"])
def create_hotel(hotel_id: str = Query(..., min_length=3)):
    hotel_id = hotel_id.lower().strip()
    with Session(engine) as session:
        if session.get(Hotel, hotel_id):
            raise HTTPException(status_code=409, detail=f"L'ID d'hôtel '{hotel_id}' existe déjà.")
        hotel = Hotel(hotel_id=hotel_id)
        session.add(hotel); session.commit()
        return {"status": "ok", "hotel_id": hotel_id}

@app.get("/hotels", tags=["Hotel Management"], response_model=List[str])
def get_all_hotels():
    with Session(engine) as session:
        return [h.hotel_id for h in session.exec(select(Hotel)).all()]

@app.delete("/hotels/{hotel_id}", tags=["Hotel Management"])
def delete_hotel(hotel_id: str):
    with Session(engine) as session:
        hotel = session.get(Hotel, hotel_id)
        if not hotel: raise HTTPException(status_code=404, detail="Hôtel non trouvé.")
        
        config = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)).first()
        if config: session.delete(config)
        
        data_path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')
        if os.path.exists(data_path): os.remove(data_path)
        
        session.delete(hotel)
        session.commit()
    return {"status": "ok", "message": f"Hôtel '{hotel_id}' et ses données supprimés."}

# --- Gestion des Fichiers ---
@app.post('/upload/excel', tags=["Uploads"])
async def upload_excel(hotel_id: str = Query(...), file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.xlsx'):
        raise HTTPException(status_code=400, detail="Format non supporté. Utilisez .xlsx")
    try:
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content), header=None)
        parsed = parse_sheet_to_structure(df)
        out_path = os.path.join(DATA_DIR, f'{hotel_id.lower()}_data.json')
        with open(out_path, 'w', encoding='utf-8') as f: json.dump(parsed, f, indent=2)
        return {'status': 'ok', 'hotel_id': hotel_id, 'rooms_found': len(parsed.get('rooms', {}))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de traitement Excel: {str(e)}")

@app.post('/upload/config', tags=["Uploads"])
async def upload_config(hotel_id: str = Query(...), file: UploadFile = File(...)):
    try:
        content = await file.read(); parsed = json.loads(content.decode('utf-8'))
        
        if parsed.get('hotel_id', '').lower() != hotel_id.lower():
            raise HTTPException(status_code=400, detail=f"Incohérence: l'ID dans le fichier ({parsed.get('hotel_id')}) ne correspond pas à l'ID sélectionné ({hotel_id}).")
        
        with Session(engine) as session:
            existing = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)).first()
            if existing: existing.config_json = json.dumps(parsed)
            else: session.add(HotelConfig(hotel_id=hotel_id, config_json=json.dumps(parsed)))
            session.commit()
        return {'status': 'ok', 'hotel_id': hotel_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de sauvegarde de la config: {str(e)}")

# --- Récupération des Données ---
@app.get('/data', tags=["Data"])
def get_data(hotel_id: str = Query(...)):
    path = os.path.join(DATA_DIR, f'{hotel_id.lower()}_data.json')
    if not os.path.exists(path): raise HTTPException(status_code=404, detail=f"Données de planning introuvables pour '{hotel_id}'.")
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

@app.get('/config', tags=["Data"])
def get_config(hotel_id: str = Query(...)):
    with Session(engine) as session:
        cfg = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id.lower())).first()
        if not cfg: raise HTTPException(status_code=404, detail=f"Configuration introuvable pour '{hotel_id}'.")
        return json.loads(cfg.config_json)

# --- Simulation ---
@app.post("/simulate", tags=["Simulation"])
async def simulate(request: SimulateIn):
    hotel_data_full = get_data(request.hotel_id)
    hotel_data = hotel_data_full.get("rooms", {})
    hotel_config = get_config(request.hotel_id)
    
    room_data = hotel_data.get(request.room)
    if not room_data: raise HTTPException(status_code=404, detail="Chambre introuvable.")
    
    plan_key = request.plan
    plan_data = room_data.get("plans", {}).get(plan_key)
    partner_info = hotel_config.get("partners", {}).get(request.partner_name, {})
    
    if not plan_data and partner_info:
        partner_codes = partner_info.get("codes", [])
        for p_name, p_data in room_data.get("plans", {}).items():
            if any(code.lower() in p_name.lower() for code in partner_codes):
                plan_key, plan_data = p_name, p_data; break
    
    if not plan_data: raise HTTPException(status_code=404, detail="Plan tarifaire introuvable ou non compatible.")

    commission_rate = partner_info.get("commission", 0) / 100.0
    discount_info = partner_info.get("defaultDiscount", {})
    
    results = []
    dstart = datetime.strptime(request.start, '%Y-%m-%d').date()
    dend = datetime.strptime(request.end, '%Y-%m-%d').date()
    
    current_date = dstart
    while current_date < dend:
        date_key = current_date.strftime("%Y-%m-%d")
        gross_price = plan_data.get(date_key)
        stock = room_data.get("stock", {}).get(date_key)
        
        price_after_discount = gross_price
        if gross_price is not None and discount_info.get("percentage", 0) > 0:
            exclude = discount_info.get("excludePlansContaining", [])
            if not any(kw.lower() in plan_key.lower() for kw in exclude):
                price_after_discount *= (1 - (discount_info.get("percentage") / 100.0))
        
        commission = price_after_discount * commission_rate if price_after_discount is not None else 0
        net_price = price_after_discount - commission if price_after_discount is not None else None

        results.append({ "date": date_key, "stock": stock, "price": gross_price, "commission": commission, "net_price": net_price })
        current_date += timedelta(days=1)

    subtotal = sum(d.get("price") or 0 for d in results)
    total_commission = sum(d.get("commission") or 0 for d in results)
    
    return { "results": results, "summary": { "subtotal": subtotal, "total_commission": total_commission, "total_net": subtotal - total_commission } }