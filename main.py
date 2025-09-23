import os, io, json
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from sqlmodel import SQLModel, Field, create_engine, Session, select
import pandas as pd
from typing import Optional
from pydantic import BaseModel

DATABASE_URL = os.getenv('DATABASE_URL', "postgresql://postgres:postgres@db:5432/hoteldb")
DATA_DIR = "/app/data"

engine = create_engine(DATABASE_URL, echo=False)

app = FastAPI(title="Hotel RM API - v1.0")


class HotelConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hotel_id: str
    config_json: str

@app.on_event('startup')
def on_startup():
    SQLModel.metadata.create_all(engine)
    os.makedirs(DATA_DIR, exist_ok=True)


def excel_serial_to_date_str(serial):
    # convert Excel serial to YYYY-MM-DD (handles common serials)
    try:
        serial = float(serial)
    except Exception:
        return None
    try:
        import datetime
        days = int(serial - 25569)
        dt = datetime.datetime.utcfromtimestamp(days * 86400)
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return None


def parse_sheet_to_structure(df):
    hotel_data = {}
    if df.shape[0] == 0:
        return hotel_data
    header = df.iloc[0].tolist()
    date_cols = []
    for j in range(3, len(header)):
        v = header[j]
        if pd.isna(v):
            continue
        if isinstance(v, (pd.Timestamp,)) :
            try:
                date_cols.append((j, pd.to_datetime(v).strftime('%Y-%m-%d')))
            except Exception:
                date_cols.append((j, str(v)))
        elif isinstance(v, (int, float)):
            d = excel_serial_to_date_str(v)
            if d:
                date_cols.append((j, d))
            else:
                date_cols.append((j, str(v)))
        else:
            try:
                date_cols.append((j, pd.to_datetime(v).strftime('%Y-%m-%d')))
            except Exception:
                date_cols.append((j, str(v)))
    current_room = None
    for i in range(1, df.shape[0]):
        row = df.iloc[i].tolist()
        if len(row) < 3:
            continue
        if not pd.isna(row[0]) and str(row[0]).strip() != '':
            current_room = str(row[0]).strip()
        descriptor = str(row[2]) if not pd.isna(row[2]) else ''
        if not current_room or descriptor == '':
            continue
        if current_room not in hotel_data:
            hotel_data[current_room] = {'stock': {}, 'plans': {}}
        lower_desc = descriptor.lower()
        if 'left for sale' in lower_desc:
            for (col_idx, date_str) in date_cols:
                val = row[col_idx] if col_idx < len(row) else None
                hotel_data[current_room]['stock'][date_str] = int(val) if pd.notna(val) and str(val).strip() != '' else None
        elif 'price' in lower_desc and 'eur' in lower_desc:
            rate_plan = str(row[1]).strip() if not pd.isna(row[1]) else None
            if not rate_plan:
                continue
            if rate_plan not in hotel_data[current_room]['plans']:
                hotel_data[current_room]['plans'][rate_plan] = {}
            for (col_idx, date_str) in date_cols:
                val = row[col_idx] if col_idx < len(row) else None
                hotel_data[current_room]['plans'][rate_plan][date_str] = float(val) if pd.notna(val) and str(val).strip() != '' else None
    return hotel_data


@app.post('/upload/excel')
async def upload_excel(hotel_id: str = Query('default'), file: UploadFile = File(...)):
    content = await file.read()
    try:
        xlsx_io = io.BytesIO(content)
        df = pd.read_excel(xlsx_io, sheet_name=0, header=None, engine='openpyxl')
        parsed = parse_sheet_to_structure(df)
        out_parsed = os.path.join(DATA_DIR, f'{hotel_id}_parsed.json')
        out_raw = os.path.join(DATA_DIR, f'{hotel_id}_raw.json')
        with open(out_parsed, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
        raw_list = df.fillna('').values.tolist()
        with open(out_raw, 'w', encoding='utf-8') as f:
            json.dump(raw_list, f, ensure_ascii=False, indent=2)
        return {'status': 'ok', 'hotel_id': hotel_id, 'rooms': list(parsed.keys())}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    from datetime import datetime, timedelta
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