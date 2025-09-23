import os, io, json
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware  # <--- IMPORTAJOUTÉ
from sqlmodel import SQLModel, Field, create_engine, Session, select
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

DATABASE_URL = os.getenv('DATABASE_URL', "postgresql://postgres:postgres@db:5432/hoteldb")
DATA_DIR = "/app/data"

engine = create_engine(DATABASE_URL.replace("postgres://", "postgresql+psycopg2://"), echo=False)

app = FastAPI(title="Hotel RM API - v1.1 CORS Fixed")

# --- CONFIGURATION CORS (SECTION AJOUTÉE) ---
# On autorise toutes les origines pour le développement.
# En production, on pourrait restreindre à un domaine spécifique.
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- FIN DE LA SECTION CORS ---

class HotelConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hotel_id: str
    config_json: str

@app.on_event('startup')
def on_startup():
    SQLModel.metadata.create_all(engine)
    os.makedirs(DATA_DIR, exist_ok=True)

def parse_sheet_to_structure(df):
    # (La logique de parsing reste la même, elle est déjà bonne)
    hotel_data = {}
    if df.shape[0] == 0:
        return hotel_data
    header = df.iloc[0].tolist()
    date_cols = []
    for j in range(3, len(header)):
        v = header[j]
        if pd.isna(v): continue
        try:
            date_cols.append((j, pd.to_datetime(v).strftime('%Y-%m-%d')))
        except Exception:
            # Gérer les dates au format numérique d'Excel
            try:
                import datetime
                days = int(float(v) - 25569)
                dt = datetime.datetime.utcfromtimestamp(days * 86400)
                date_cols.append((j, dt.strftime('%Y-%m-%d')))
            except Exception:
                continue
    
    current_room = None
    for i in range(1, df.shape[0]):
        row = df.iloc[i].tolist()
        if len(row) < 3: continue
        if pd.notna(row[0]) and str(row[0]).strip() != '':
            current_room = str(row[0]).strip()
        
        descriptor = str(row[2]) if pd.notna(row[2]) else ''
        if not current_room or descriptor == '': continue

        if current_room not in hotel_data:
            hotel_data[current_room] = {'stock': {}, 'plans': {}}

        lower_desc = descriptor.lower()
        if 'left for sale' in lower_desc:
            for (col_idx, date_str) in date_cols:
                val = row[col_idx] if col_idx < len(row) and pd.notna(row[col_idx]) else '0'
                val_str = str(val).strip()
                hotel_data[current_room]['stock'][date_str] = int(float(val_str)) if val_str.replace('.','',1).isdigit() else 0
        
        elif 'price' in lower_desc:
            rate_plan = str(row[1]).strip() if pd.notna(row[1]) else None
            if not rate_plan: continue
            if rate_plan not in hotel_data[current_room]['plans']:
                hotel_data[current_room]['plans'][rate_plan] = {}
            for (col_idx, date_str) in date_cols:
                val = row[col_idx] if col_idx < len(row) and pd.notna(row[col_idx]) else None
                price_val = None
                if val:
                    try:
                        price_val = float(str(val).replace(',', '.'))
                    except (ValueError, TypeError):
                        price_val = None
                hotel_data[current_room]['plans'][rate_plan][date_str] = price_val
    return hotel_data

# --- ENDPOINT UPLOAD AMÉLIORÉ ---
@app.post('/upload/excel')
async def upload_excel(hotel_id: str = Query('default'), file: UploadFile = File(...)):
    content = await file.read()
    filename = file.filename.lower()
    try:
        if filename.endswith('.csv'):
            csv_io = io.StringIO(content.decode('utf-8'))
            df = pd.read_csv(csv_io, sep=';', header=None)
        elif filename.endswith('.xlsx'):
            xlsx_io = io.BytesIO(content)
            df = pd.read_excel(xlsx_io, header=None, engine='openpyxl')
        else:
            raise HTTPException(status_code=400, detail="Format non supporté. Utilisez .csv ou .xlsx")

        parsed = parse_sheet_to_structure(df)
        
        out_parsed = os.path.join(DATA_DIR, f'{hotel_id}_parsed.json')
        with open(out_parsed, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
        
        return {'status': 'ok', 'hotel_id': hotel_id, 'rooms': list(parsed.keys())}
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=400, detail=f"Erreur lors du traitement du fichier: {str(e)}")

# Le reste des endpoints (config, data, simulate) reste identique
@app.post('/upload/config')
async def upload_config(file: UploadFile = File(...)):
    content = await file.read()
    try:
        parsed = json.loads(content.decode('utf-8'))
        hotel_id = parsed.get('hotel_id', 'default')
        cfg_str = json.dumps(parsed)
        with Session(engine) as session:
            q = select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)
            existing = session.exec(q).first()
            if existing:
                existing.config_json = cfg_str
                session.add(existing)
            else:
                session.add(HotelConfig(hotel_id=hotel_id, config_json=cfg_str))
            session.commit()
        return {'status': 'ok', 'hotel_id': hotel_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get('/data')
def get_data(hotel_id: str = Query('default')):
    path = os.path.join(DATA_DIR, f'{hotel_id}_parsed.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

@app.get('/config')
def get_config(hotel_id: str = Query('default')):
    with Session(engine) as session:
        q = select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)
        cfg = session.exec(q).first()
        if cfg:
            return json.loads(cfg.config_json)
        return {}

class SimulateIn(BaseModel):
    hotel_id: str
    room: str
    plan: str
    start: str
    end: str
    partner: Optional[str] = None

@app.post('/simulate')
def simulate(payload: SimulateIn):
    path = os.path.join(DATA_DIR, f'{payload.hotel_id}_parsed.json')
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail='No data for hotel')
    with open(path, 'r', encoding='utf-8') as f:
        hotel = json.load(f)
    room = hotel.get(payload.room)
    if not room:
        raise HTTPException(status_code=404, detail='Room not found')
    results = []
    dstart = datetime.strptime(payload.start, '%Y-%m-%d')
    dend = datetime.strptime(payload.end, '%Y-%m-%d')
    cur = dstart
    while cur < dend:
        key = cur.strftime('%Y-%m-%d')
        price = None
        stock = None
        try:
            price = room['plans'][payload.plan].get(key)
        except Exception:
            price = None
        try:
            stock = room['stock'].get(key)
        except Exception:
            stock = None
        results.append({'date': key, 'price': price, 'stock': stock})
        cur += timedelta(days=1)
    subtotal = sum([r['price'] for r in results if r['price']])
    return {'results': results, 'subtotal': subtotal}