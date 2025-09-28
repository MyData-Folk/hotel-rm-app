import os
import io
import json
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Field, create_engine, Session, select
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

# --- Configuration ---
# L'URL de la base de données est récupérée depuis les variables d'environnement de Coolify
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///local.db") # Fallback sur une DB locale
DATA_DIR = "/app/data" # Coolify fournira un volume persistant ici

# Conversion de l'URL pour SQLAlchemy/Psycopg2
engine = create_engine(DATABASE_URL.replace("postgres://", "postgresql+psycopg2://"), echo=False)

app = FastAPI(
    title="Hotel RM API - v5.0 (Final)",
    description="API pour la gestion complète des données et de la configuration hôtelière."
)

# --- Configuration CORS ---
origins = [ "https://folkestone.e-hotelmanager.com", "https://admin-folkestone.e-hotelmanager.com" ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- Modèles de Données ---
class HotelConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hotel_id: str = Field(index=True, unique=True)
    config_json: str

class SimulateIn(BaseModel):
    hotel_id: str; room: str; plan: str; start: str; end: str
    partner_name: Optional[str] = None

# --- Événements de Démarrage ---
@app.on_event('startup')
def on_startup():
    SQLModel.metadata.create_all(engine)
    os.makedirs(DATA_DIR, exist_ok=True)

# --- Fonctions Utilitaires ---
def parse_sheet_to_structure(df: pd.DataFrame) -> dict:
    hotel_data = {}
    if df.shape[0] < 1: return hotel_data
    header_row = df.iloc[0].tolist()
    date_cols = []
    for j, col_value in enumerate(header_row):
        if j < 3 or pd.isna(col_value): continue
        date_str = None
        try:
            if isinstance(col_value, (int, float)):
                base_date = datetime(1899, 12, 30); delta = timedelta(days=col_value)
                date_str = (base_date + delta).strftime('%Y-%m-%d')
            else:
                date_str = pd.to_datetime(str(col_value), dayfirst=True).strftime('%Y-%m-%d')
            if date_str: date_cols.append({'index': j, 'date': date_str})
        except Exception: continue
    
    current_room = None
    for i in range(1, df.shape[0]):
        row = df.iloc[i].tolist()
        if pd.notna(row[0]) and str(row[0]).strip(): current_room = str(row[0]).strip()
        if not current_room or len(row) < 3: continue
        descriptor = str(row[2]) if pd.notna(row[2]) else ''
        if not descriptor: continue
        if current_room not in hotel_data: hotel_data[current_room] = {'stock': {}, 'plans': {}}
        lower_desc = descriptor.lower()
        if 'left for sale' in lower_desc:
            for date_info in date_cols:
                col_idx, date_str = date_info['index'], date_info['date']
                stock_val = 0
                if col_idx < len(row) and pd.notna(row[col_idx]):
                    try: stock_val = int(float(row[col_idx]))
                    except (ValueError, TypeError): stock_val = 0
                hotel_data[current_room]['stock'][date_str] = stock_val
        elif 'price' in lower_desc:
            rate_plan = str(row[1]).strip() if pd.notna(row[1]) else None
            if not rate_plan: continue
            if rate_plan not in hotel_data[current_room]['plans']: hotel_data[current_room]['plans'][rate_plan] = {}
            for date_info in date_cols:
                col_idx, date_str = date_info['index'], date_info['date']
                price_val = None
                if col_idx < len(row) and pd.notna(row[col_idx]):
                    try: price_val = float(str(row[col_idx]).replace(',', '.'))
                    except (ValueError, TypeError): price_val = None
                hotel_data[current_room]['plans'][rate_plan][date_str] = price_val
    return hotel_data

# --- Endpoints ---
@app.get("/", tags=["Status"])
def read_root(): return {"status": "Hotel RM API is running"}

@app.post('/upload/excel', tags=["Uploads"])
async def upload_excel(hotel_id: str = Query(...), file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="Format non supporté. Utilisez .xlsx ou .csv")
    try:
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content), header=None)
        parsed = parse_sheet_to_structure(df)
        out_path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')
        with open(out_path, 'w', encoding='utf-8') as f: json.dump(parsed, f, indent=2)
        return {'status': 'ok', 'hotel_id': hotel_id, 'rooms_found': len(parsed)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de traitement Excel: {str(e)}")

@app.post('/upload/config', tags=["Uploads"])
async def upload_config(file: UploadFile = File(...)):
    try:
        content = await file.read(); parsed = json.loads(content.decode('utf-8'))
        hotel_id = parsed.get('hotel_id')
        if not hotel_id: raise HTTPException(status_code=400, detail="La clé 'hotel_id' est manquante.")
        cfg_str = json.dumps(parsed)
        with Session(engine) as session:
            existing = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)).first()
            if existing: existing.config_json = cfg_str; session.add(existing)
            else: session.add(HotelConfig(hotel_id=hotel_id, config_json=cfg_str))
            session.commit()
        return {'status': 'ok', 'hotel_id': hotel_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de sauvegarde config: {str(e)}")

@app.get('/data', tags=["Data"])
def get_data(hotel_id: str = Query(...)):
    path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')
    if not os.path.exists(path): raise HTTPException(status_code=404, detail=f"Données introuvables pour '{hotel_id}'.")
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

@app.get('/config', tags=["Data"])
def get_config(hotel_id: str = Query(...)):
    with Session(engine) as session:
        cfg = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)).first()
        if not cfg: raise HTTPException(status_code=404, detail=f"Configuration introuvable pour '{hotel_id}'.")
        return json.loads(cfg.config_json)

@app.post("/simulate", tags=["Simulation"])
async def simulate(request: SimulateIn):
    hotel_data = get_data(request.hotel_id)
    hotel_config = get_config(request.hotel_id)
    
    room_data = hotel_data.get(request.room)
    if not room_data: raise HTTPException(status_code=404, detail=f"Chambre '{request.room}' introuvable.")
    plan_data = room_data.get("plans", {}).get(request.plan)
    if not plan_data: raise HTTPException(status_code=404, detail=f"Plan '{request.plan}' introuvable.")

    partner_info = hotel_config.get("partners", {}).get(request.partner_name, {})
    commission_rate = partner_info.get("commission", 0) / 100.0 if partner_info else 0
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
        if gross_price is not None and discount_info:
            if discount_info.get("percentage", 0) > 0:
                exclude = discount_info.get("excludePlansContaining", [])
                if not any(kw.lower() in request.plan.lower() for kw in exclude):
                    price_after_discount *= (1 - (discount_info.get("percentage", 0) / 100.0))
        
        commission = price_after_discount * commission_rate if price_after_discount is not None else 0
        net_price = price_after_discount - commission if price_after_discount is not None else None

        results.append({ "date": date_key, "stock": stock, "price": gross_price, "commission": commission, "net_price": net_price })
        current_date += timedelta(days=1)

    subtotal = sum(d["price"] or 0 for d in results)
    total_commission = sum(d["commission"] or 0 for d in results)
    total_net = subtotal - total_commission
    
    return { "results": results, "summary": { "subtotal": subtotal, "total_commission": total_commission, "total_net": total_net } }