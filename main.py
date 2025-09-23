import os
import io
import json
import pandas as pd
import traceback
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Field, create_engine, Session, select
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

# --- Configuration ---
DATABASE_URL = os.getenv('DATABASE_URL', "postgresql://postgres:postgres@db:5432/hoteldb")
DATA_DIR = "/app/data"

# Utiliser l'URL modifiée pour assurer la compatibilité avec psycopg2
engine = create_engine(DATABASE_URL.replace("postgres://", "postgresql+psycopg2://"), echo=False)

app = FastAPI(title="Hotel RM API - v1.2 Robust Parser")

# --- Configuration CORS ---
# Autorise les requêtes provenant de n'importe quelle origine.
origins = ["*"]

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

# --- Événements de Démarrage de l'Application ---
@app.on_event('startup')
def on_startup():
    SQLModel.metadata.create_all(engine)
    os.makedirs(DATA_DIR, exist_ok=True)

# --- Fonction de Parsing de Fichier (Améliorée) ---
def parse_sheet_to_structure(df):
    hotel_data = {}
    if df.shape[0] < 1:
        return hotel_data

    header_row = df.iloc[0].tolist()
    date_cols = []
    
    # Itération sur les colonnes de l'en-tête pour trouver les dates
    for j, col_value in enumerate(header_row):
        if j < 3 or pd.isna(col_value):
            continue
        
        date_str = None
        try:
            if isinstance(col_value, (int, float)):
                # Gérer les dates au format numérique d'Excel
                base_date = datetime(1899, 12, 30)
                delta = timedelta(days=col_value)
                date_str = (base_date + delta).strftime('%Y-%m-%d')
            else:
                # Gérer les dates textuelles (ex: '22/09/2025')
                date_str = pd.to_datetime(str(col_value), dayfirst=True).strftime('%Y-%m-%d')
            
            if date_str:
                date_cols.append({'index': j, 'date': date_str})
        except Exception:
            print(f"Avertissement: Impossible de convertir la colonne d'en-tête '{col_value}' en date. Elle sera ignorée.")
            continue

    current_room = None
    # Itération sur chaque ligne de données
    for i in range(1, df.shape[0]):
        if df.iloc[i].isnull().all():
            continue
        
        row = df.iloc[i].tolist()
        
        if pd.notna(row[0]) and str(row[0]).strip():
            current_room = str(row[0]).strip()
        
        if not current_room or len(row) < 3:
            continue

        descriptor = str(row[2]) if pd.notna(row[2]) else ''
        if not descriptor:
            continue

        if current_room not in hotel_data:
            hotel_data[current_room] = {'stock': {}, 'plans': {}}

        lower_desc = descriptor.lower()
        
        try:
            if 'left for sale' in lower_desc:
                for date_info in date_cols:
                    col_idx, date_str = date_info['index'], date_info['date']
                    stock_val = '0'
                    if col_idx < len(row) and pd.notna(row[col_idx]):
                        stock_val = str(row[col_idx]).strip()
                    # Gère les nombres et les 'X' ou autres textes
                    hotel_data[current_room]['stock'][date_str] = int(float(stock_val)) if stock_val.replace('.','',1).isdigit() else 0

            elif 'price' in lower_desc:
                rate_plan = str(row[1]).strip() if pd.notna(row[1]) else None
                if not rate_plan:
                    continue
                if rate_plan not in hotel_data[current_room]['plans']:
                    hotel_data[current_room]['plans'][rate_plan] = {}
                for date_info in date_cols:
                    col_idx, date_str = date_info['index'], date_info['date']
                    price_val = None
                    if col_idx < len(row) and pd.notna(row[col_idx]):
                        try:
                            # Gère les nombres avec virgule décimale
                            price_val = float(str(row[col_idx]).replace(',', '.'))
                        except (ValueError, TypeError):
                            price_val = None
                    hotel_data[current_room]['plans'][rate_plan][date_str] = price_val
        except Exception as line_error:
            print(f"Erreur en traitant la ligne {i+1} pour la chambre '{current_room}': {line_error}")
            continue
            
    return hotel_data

# --- Endpoints de l'API ---

@app.post('/upload/excel')
async def upload_excel(hotel_id: str = Query('default'), file: UploadFile = File(...)):
    print(f"Début de l'upload pour l'hôtel: {hotel_id}, fichier: {file.filename}")
    try:
        content = await file.read()
        filename = file.filename.lower()
        
        if filename.endswith('.csv'):
            print("Détection d'un fichier CSV...")
            # Utiliser un fallback pour l'encodage si l'UTF-8 échoue
            try:
                decoded_content = content.decode('utf-8')
            except UnicodeDecodeError:
                print("Décodage UTF-8 échoué, tentative avec latin-1...")
                decoded_content = content.decode('latin-1')
            csv_io = io.StringIO(decoded_content)
            df = pd.read_csv(csv_io, sep=';', header=None)
        elif filename.endswith('.xlsx'):
            print("Détection d'un fichier XLSX...")
            xlsx_io = io.BytesIO(content)
            df = pd.read_excel(xlsx_io, header=None, engine='openpyxl')
        else:
            raise HTTPException(status_code=400, detail="Format non supporté. Utilisez .csv ou .xlsx")
        
        print("Fichier lu avec Pandas, début du parsing...")
        parsed = parse_sheet_to_structure(df)
        print("Parsing terminé avec succès.")
        
        out_parsed = os.path.join(DATA_DIR, f'{hotel_id}_parsed.json')
        with open(out_parsed, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
        
        print(f"Fichier de résultat sauvegardé pour {hotel_id}. Upload terminé.")
        return {'status': 'ok', 'hotel_id': hotel_id, 'rooms': list(parsed.keys())}
    except Exception as e:
        print("--- ERREUR CRITIQUE PENDANT L'UPLOAD ---")
        print(traceback.format_exc())
        print("-----------------------------------------")
        raise HTTPException(status_code=500, detail=f"Une erreur interne est survenue: {str(e)}")


@app.post('/upload/config')
async def upload_config(file: UploadFile = File(...)):
    content = await file.read()
    try:
        parsed = json.loads(content.decode('utf-8'))
        hotel_id = parsed.get('hotel_id', 'default')
        cfg_str = json.dumps(parsed)
        with Session(engine) as session:
            q = select(HotelConfig).where(Hotel_config.hotel_id == hotel_id)
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