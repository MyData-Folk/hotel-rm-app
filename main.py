import os
import io
import json
import pandas as pd
import traceback
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles # IMPORTANT
from fastapi.responses import FileResponse    # IMPORTANT
from sqlmodel import SQLModel, Field, create_engine, Session, select
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta

# --- Configuration ---
DATABASE_URL = os.getenv('DATABASE_URL', "postgresql://postgres:postgres@db:5432/hoteldb")
DATA_DIR = "/app/data"

engine = create_engine(DATABASE_URL.replace("postgres://", "postgresql+psycopg2://"), echo=False)

app = FastAPI(title="Hotel RM API - v2.1 Final")

# --- Configuration CORS ---
origins = ["*"] # On autorise tout pour la simplicité
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Modèles de Base de Données ---
class HotelConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hotel_id: str
    config_json: str

@app.on_event('startup')
def on_startup():
    SQLModel.metadata.create_all(engine)
    os.makedirs(DATA_DIR, exist_ok=True)

# --- Fonction de Parsing (inchangée) ---
def parse_sheet_to_structure(df: pd.DataFrame) -> Dict[str, Any]:
    # ... (la fonction de parsing reste identique à la précédente, pas besoin de la recopier)
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
        except Exception:
            print(f"Avertissement: Impossible de convertir l'en-tête '{col_value}' en date. Colonne ignorée.")
            continue
    current_room = None
    for i in range(1, df.shape[0]):
        if df.iloc[i].isnull().all(): continue
        row = df.iloc[i].tolist()
        if pd.notna(row[0]) and str(row[0]).strip(): current_room = str(row[0]).strip()
        if not current_room or len(row) < 3: continue
        descriptor = str(row[2]) if pd.notna(row[2]) else ''
        if not descriptor: continue
        if current_room not in hotel_data: hotel_data[current_room] = {'stock': {}, 'plans': {}}
        lower_desc = descriptor.lower()
        try:
            if 'left for sale' in lower_desc:
                for date_info in date_cols:
                    col_idx, date_str = date_info['index'], date_info['date']
                    stock_val = '0'
                    if col_idx < len(row) and pd.notna(row[col_idx]): stock_val = str(row[col_idx]).strip()
                    hotel_data[current_room]['stock'][date_str] = int(float(stock_val)) if stock_val.replace('.','',1).isdigit() else 0
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
        except Exception as line_error:
            print(f"Erreur en traitant la ligne {i+1} pour '{current_room}': {line_error}")
            continue
    return hotel_data

# --- Endpoints de l'API (inchangés) ---
@app.post('/upload/excel', tags=["API"])
async def upload_excel(hotel_id: str = Query('default'), file: UploadFile = File(...)):
    # ... (code de la fonction identique)
    print(f"Début de l'upload de données pour l'hôtel: {hotel_id}, fichier: {file.filename}")
    try:
        content = await file.read(); filename = file.filename.lower()
        if filename.endswith('.csv'): df = pd.read_csv(io.StringIO(content.decode('utf-8')), sep=';', header=None)
        elif filename.endswith('.xlsx'): df = pd.read_excel(io.BytesIO(content), header=None, engine='openpyxl')
        else: raise HTTPException(status_code=400, detail="Format non supporté. Utilisez .csv ou .xlsx")
        parsed = parse_sheet_to_structure(df)
        out_parsed = os.path.join(DATA_DIR, f'{hotel_id}_parsed.json')
        with open(out_parsed, 'w', encoding='utf-8') as f: json.dump(parsed, f, ensure_ascii=False, indent=2)
        print(f"Upload de données terminé avec succès pour {hotel_id}.")
        return {'status': 'ok', 'hotel_id': hotel_id, 'rooms_found': len(parsed.keys())}
    except Exception as e:
        print(f"--- ERREUR CRITIQUE PENDANT L'UPLOAD DE DONNÉES ---\n{traceback.format_exc()}\n-----------------------------------------")
        raise HTTPException(status_code=500, detail=f"Une erreur interne est survenue: {str(e)}")

@app.post('/upload/config', tags=["API"])
async def upload_config(file: UploadFile = File(...)):
    # ... (code de la fonction identique)
    try:
        content = await file.read(); parsed = json.loads(content.decode('utf-8'))
        hotel_id = parsed.get('hotel_id')
        if not hotel_id: raise HTTPException(status_code=400, detail="Le fichier JSON doit contenir une clé 'hotel_id'.")
        cfg_str = json.dumps(parsed)
        with Session(engine) as session:
            q = select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)
            existing = session.exec(q).first()
            if existing: existing.config_json = cfg_str; session.add(existing)
            else: session.add(HotelConfig(hotel_id=hotel_id, config_json=cfg_str))
            session.commit()
        return {'status': 'ok', 'hotel_id': hotel_id}
    except Exception as e:
        print(f"--- ERREUR CRITIQUE PENDANT L'UPLOAD DE CONFIG ---\n{traceback.format_exc()}\n-----------------------------------------")
        raise HTTPException(status_code=500, detail=f"Une erreur interne est survenue: {str(e)}")

@app.get('/data', tags=["API"])
def get_data(hotel_id: str = Query('default')) -> Dict[str, Any]:
    # ... (code de la fonction identique)
    path = os.path.join(DATA_DIR, f'{hotel_id}_parsed.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: return json.load(f)
    raise HTTPException(status_code=404, detail=f"Aucune donnée trouvée pour l'hôtel '{hotel_id}'")

@app.get('/config', tags=["API"])
def get_config(hotel_id: str = Query('default')) -> Dict[str, Any]:
    # ... (code de la fonction identique)
    with Session(engine) as session:
        q = select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)
        cfg = session.exec(q).first()
        if cfg: return json.loads(cfg.config_json)
        raise HTTPException(status_code=404, detail=f"Aucune configuration trouvée pour l'hôtel '{hotel_id}'")

class SimulateIn(BaseModel):
    hotel_id: str; room: str; plan: str; start: str; end: str; partner_id: Optional[str] = None

@app.post('/simulate', tags=["API"])
def simulate(payload: SimulateIn) -> Dict[str, Any]:
    # ... (code de la fonction identique)
    data = get_data(payload.hotel_id); config = get_config(payload.hotel_id)
    room_data = data.get(payload.room)
    if not room_data: raise HTTPException(status_code=404, detail=f"Type de chambre '{payload.room}' non trouvé")
    plan_data = room_data.get('plans', {}).get(payload.plan)
    if not plan_data: raise HTTPException(status_code=404, detail=f"Plan tarifaire '{payload.plan}' non trouvé pour cette chambre")
    commission_rate = 0.0
    if payload.partner_id:
        partner = next((p for p in config.get("ota_partners", []) if p["id"] == payload.partner_id), None)
        if partner: commission_rate = partner.get("commission", 0) / 100.0
    results = []; dstart = datetime.strptime(payload.start, '%Y-%m-%d'); dend = datetime.strptime(payload.end, '%Y-%m-%d')
    current_date = dstart
    while current_date < dend:
        date_key = current_date.strftime('%Y-%m-%d')
        price = plan_data.get(date_key); stock = room_data.get('stock', {}).get(date_key)
        commission = (price * commission_rate) if price is not None else 0
        net_price = (price - commission) if price is not None else 0
        results.append({'date': date_key, 'price': price, 'stock': stock, 'commission': round(commission, 2), 'net_price': round(net_price, 2)})
        current_date += timedelta(days=1)
    subtotal = sum(r['price'] for r in results if r.get('price') is not None)
    total_commission = sum(r['commission'] for r in results if r.get('commission') is not None)
    return {'results': results, 'summary': {'subtotal': round(subtotal, 2), 'total_commission': round(total_commission, 2), 'total_net': round(subtotal - total_commission, 2)}}

# --- SECTION POUR SERVIR LE FRONTEND ---
# La ligne suivante doit être la dernière configuration de l'app

@app.get("/admin", response_class=FileResponse, tags=["Frontend"])
async def read_admin_page():
    return 'static/admin.html'

@app.get("/frontend", response_class=FileResponse, tags=["Frontend"])
async def read_frontend_page():
    return 'static/frontend.html'

app.mount("/", StaticFiles(directory="static", html=True), name="static")