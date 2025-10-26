import os
import io
import json
import re
import logging
import urllib.parse
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import mimetypes

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlmodel import SQLModel, Field, create_engine, Session, select, func

# --- 1. CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///local.db")
# Racine persistante demandée
DATA_DIR = os.getenv("DATA_DIR", "/mydata/hotels")

os.makedirs(DATA_DIR, exist_ok=True)

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("hotel-rm-api")

# Adapter l'URL pour psycopg2 si besoin
engine = create_engine(DATABASE_URL.replace("postgres://", "postgresql+psycopg2://"), echo=False)

app = FastAPI(
    title="Hotel RM API - v9.2 (Multi-Hotel)",
    description="API complète pour la gestion des données hôtelières, simulations et stockage persistant par hôtel."
)

# --- 2. MIDDLEWARE CORS + ERREURS ---
origins = [
    "https://hotel.hotelmanager.fr",
    "https://admin.hotelmanager.fr",
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://localhost:8080",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:8000",
    "https://localhost",
    "https://localhost:3000",
    "https://localhost:5173",
    "https://127.0.0.1:3000",
    "*",  # à restreindre en prod
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"]
)

@app.middleware("http")
async def catch_exceptions_middleware(request, call_next):
    try:
        response = await call_next(request)
        # Entêtes CORS universelles (ajoutées en plus du middleware)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response
    except Exception as e:
        logger.error(f"Erreur non gérée: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erreur interne du serveur"},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                "Access-Control-Allow-Headers": "*"
            }
        )

@app.options("/{rest_of_path:path}")
async def preflight_handler(request, rest_of_path: str):
    return JSONResponse(
        content={"status": "OK"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400"
        }
    )

# --- 3. OUTILS ---
def decode_hotel_id(hotel_id: str) -> str:
    return urllib.parse.unquote(hotel_id).lower().strip()

def get_hotel_dir(hotel_id: str) -> str:
    path = os.path.join(DATA_DIR, hotel_id)
    os.makedirs(path, exist_ok=True)
    return path

def safe_int(val) -> int:
    if pd.isna(val) or val is None:
        return 0
    try:
        if isinstance(val, str):
            val = val.strip().upper()
            if val in ('X', 'N/A', '-', ''):
                return 0
            val = re.sub(r'[^\d]', '', val)
            if not val:
                return 0
        return int(float(str(val).replace(',', '.')))
    except (ValueError, TypeError, AttributeError):
        return 0

def log_activity(
    session: Session,
    activity_type: str,
    description: str,
    hotel_id: Optional[str] = None,
    performed_by: str = "system",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        payload = ActivityLog(
            hotel_id=hotel_id,
            activity_type=activity_type,
            description=description,
            performed_by=performed_by,
            details=json.dumps(details or {}, ensure_ascii=False),
        )
        session.add(payload)
    except Exception as exc:
        logger.error(f"Impossible d'enregistrer l'activité '{activity_type}': {exc}")

def deserialize_details(raw_details: Optional[str]) -> Optional[Dict[str, Any]]:
    if raw_details in (None, "", "null"):
        return None
    try:
        return json.loads(raw_details)
    except json.JSONDecodeError:
        return {"raw": raw_details}

def get_system_metrics(session: Session) -> Dict[str, Any]:
    active_hotels = session.exec(
        select(func.count(Hotel.id)).where(Hotel.is_active == True)
    ).one()
    if isinstance(active_hotels, tuple):
        active_hotels = active_hotels[0]

    total_hotels = session.exec(select(func.count(Hotel.id))).one()
    if isinstance(total_hotels, tuple):
        total_hotels = total_hotels[0]
    recent_logs = session.exec(
        select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(5)
    ).all()

    return {
        "active_hotels": active_hotels,
        "total_hotels": total_hotels,
        "recent_activity": [
            {
                "id": log.id,
                "hotel_id": log.hotel_id,
                "activity_type": log.activity_type,
                "description": log.description,
                "details": deserialize_details(log.details),
                "performed_by": log.performed_by,
                "created_at": log.created_at.isoformat(),
            }
            for log in recent_logs
        ],
    }

def parse_sheet_to_structure(df: pd.DataFrame) -> dict:
    """
    Parser adapté à la structure réelle des fichiers (xls/csv) :
    - Ligne 1 = A1 = source
    - Col 0 = chambre, Col1 = plan, Col2 = 'Left for sale' / 'Price (EUR)'
    - Colonnes de dates à partir de j >= 3
    """
    hotel_data = {}
    if df.shape[0] < 1:
        return {}

    source_info = str(df.iloc[0, 0]) if df.shape[0] > 0 and df.shape[1] > 0 else "Source inconnue"

    header_row = df.iloc[0].tolist()
    date_cols = []
    for j, col_value in enumerate(header_row):
        if pd.isna(col_value) or j < 3:
            continue
        try:
            date_str = None
            if isinstance(col_value, str) and '/' in col_value:
                day, month, year = col_value.split('/')
                date_str = f"20{year}-{month.zfill(2)}-{day.zfill(2)}"
            elif isinstance(col_value, (datetime, pd.Timestamp)):
                date_str = col_value.strftime('%Y-%m-%d')
            elif isinstance(col_value, (int, float)):
                date_str = (datetime(1899, 12, 30) + timedelta(days=col_value)).strftime('%Y-%m-%d')
            else:
                date_str = pd.to_datetime(str(col_value), dayfirst=True).strftime('%Y-%m-%d')
            if date_str and date_str.startswith('20'):
                date_cols.append({'index': j, 'date': date_str})
        except Exception as e:
            logger.warning(f"Impossible de parser la date {col_value}: {e}")
            continue

    current_room = None
    current_stock_data = {}

    for i in range(1, df.shape[0]):
        row = df.iloc[i].tolist()
        if all(pd.isna(cell) for cell in row[:3]):
            continue

        if pd.notna(row[0]) and str(row[0]).strip():
            current_room = str(row[0]).strip()
        if not current_room:
            continue

        if current_room not in hotel_data:
            hotel_data[current_room] = {'stock': {}, 'plans': {}}

        descriptor = str(row[2]).strip().lower() if pd.notna(row[2]) else ""

        if 'left for sale' in descriptor:
            current_stock_data = {}
            for dc in date_cols:
                if dc['index'] < len(row):
                    current_stock_data[dc['date']] = safe_int(row[dc['index']])
            hotel_data[current_room]['stock'] = current_stock_data

        elif 'price' in descriptor and current_stock_data:
            plan_name = str(row[1]).strip() if pd.notna(row[1]) else "UNNAMED_PLAN"
            if plan_name not in hotel_data[current_room]['plans']:
                hotel_data[current_room]['plans'][plan_name] = {}
            for dc in date_cols:
                if dc['index'] < len(row):
                    price_value = row[dc['index']]
                    try:
                        if pd.notna(price_value):
                            price_str = str(price_value).replace(',', '.')
                            price_clean = re.sub(r'[^\d.]', '', price_str)
                            hotel_data[current_room]['plans'][plan_name][dc['date']] = float(price_clean)
                        else:
                            hotel_data[current_room]['plans'][plan_name][dc['date']] = None
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Erreur conversion prix {price_value}: {e}")
                        hotel_data[current_room]['plans'][plan_name][dc['date']] = None

    logger.info(f"Parsing terminé: {len(hotel_data)} chambres, {len(date_cols)} dates")
    return {
        'report_generated_at': source_info,
        'rooms': hotel_data,
        'dates_processed': [dc['date'] for dc in date_cols]
    }

# --- 4. MODÈLES DE DONNÉES ---
class Hotel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hotel_id: str = Field(index=True, unique=True)
    name: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)

class HotelConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hotel_id: str = Field(index=True, unique=True)
    config_json: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hotel_id: Optional[str] = Field(default=None, index=True)
    activity_type: str = Field(index=True)
    description: str
    details: Optional[str] = None
    performed_by: Optional[str] = Field(default="system", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

class HotelCreate(BaseModel):
    hotel_id: str
    name: Optional[str] = None

class HotelOut(BaseModel):
    hotel_id: str
    name: Optional[str] = None
    is_active: bool
    created_at: datetime

class ActivityLogOut(BaseModel):
    id: int
    hotel_id: Optional[str]
    activity_type: str
    description: str
    details: Optional[Dict[str, Any]] = None
    performed_by: Optional[str]
    created_at: datetime

class SimulateIn(BaseModel):
    hotel_id: str
    room: str
    plan: str
    start: str
    end: str
    partner_name: Optional[str] = None
    apply_commission: bool = True
    apply_partner_discount: bool = True
    promo_discount: float = 0.0
    performed_by: Optional[str] = "system"

class AvailabilityRequest(BaseModel):
    hotel_id: str
    start_date: str
    end_date: str
    room_types: List[str] = []
    performed_by: Optional[str] = "system"

# --- 5. DÉMARRAGE ---
@app.on_event('startup')
def on_startup():
    SQLModel.metadata.create_all(engine)
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"Application démarrée. Répertoire persistant: {DATA_DIR}")

# --- 6. STATUS / MONITORING ---
@app.get("/", tags=["Status"])
def read_root(): 
    return {
        "status": "Hotel RM API v9.2 is running", 
        "timestamp": datetime.now().isoformat(),
        "cors_enabled": True
    }

@app.get("/health", tags=["Status"])
def health_check():
    started = datetime.utcnow()
    db_status = "unknown"
    metrics: Dict[str, Any] = {}
    try:
        with Session(engine) as session:
            session.exec(select(Hotel).limit(1))
            db_status = "healthy"
            metrics = get_system_metrics(session)
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"
    duration_ms = max((datetime.utcnow() - started).total_seconds() * 1000, 0)
    return {
        "status": "ok" if db_status == "healthy" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status,
        "version": "9.2",
        "latency_ms": round(duration_ms, 2),
        "metrics": metrics,
        "cors": "enabled",
    }

@app.get("/monitor/health", tags=["Monitoring"])
def monitor_health():
    started = datetime.utcnow()
    with Session(engine) as session:
        metrics = get_system_metrics(session)
        db_status = "healthy"

    # Comptage des fichiers *_data.json dans tous les dossiers d'hôtel
    data_files = 0
    storage_usage = 0
    for hotel in os.listdir(DATA_DIR):
        hdir = os.path.join(DATA_DIR, hotel)
        if not os.path.isdir(hdir):
            continue
        for f in os.listdir(hdir):
            if f.endswith("_data.json"):
                data_files += 1
                path = os.path.join(hdir, f)
                if os.path.exists(path):
                    storage_usage += os.path.getsize(path)

    return {
        "status": "ok",
        "generated_at": datetime.utcnow().isoformat(),
        "latency_ms": round(max((datetime.utcnow() - started).total_seconds() * 1000, 0), 2),
        "database": db_status,
        "metrics": metrics,
        "storage": {
            "files": data_files,
            "bytes": storage_usage,
        },
    }

@app.get("/activity", tags=["Monitoring"], response_model=List[ActivityLogOut])
def list_activity(limit: int = Query(20, ge=1, le=200)):
    with Session(engine) as session:
        logs = session.exec(
            select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
        ).all()
    return [
        ActivityLogOut(
            id=log.id,
            hotel_id=log.hotel_id,
            activity_type=log.activity_type,
            description=log.description,
            details=deserialize_details(log.details),
            performed_by=log.performed_by,
            created_at=log.created_at,
        )
        for log in logs
    ]

# --- 7. GESTION DES HÔTELS ---
@app.post("/hotels", tags=["Hotel Management"], response_model=HotelOut, status_code=201)
def create_hotel(payload: HotelCreate, performed_by: str = Query("system", alias="actor")):
    hotel_id = decode_hotel_id(payload.hotel_id)
    if not re.fullmatch(r"[a-z0-9-]{3,64}", hotel_id):
        raise HTTPException(status_code=400, detail="L'identifiant d'hôtel doit contenir uniquement des minuscules, chiffres ou tirets.")
    hotel_name = (payload.name or "").strip() or None

    with Session(engine) as session:
        existing = session.exec(select(Hotel).where(Hotel.hotel_id == hotel_id)).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.name = hotel_name or existing.name
                log_activity(session, "hotel.reactivated", f"Hôtel réactivé: {hotel_id}", hotel_id, performed_by, {"name": existing.name})
                session.commit()
                session.refresh(existing)
                # s'assurer que le répertoire existe
                get_hotel_dir(hotel_id)
                return HotelOut(hotel_id=existing.hotel_id, name=existing.name, is_active=existing.is_active, created_at=existing.created_at)
            raise HTTPException(status_code=409, detail=f"L'ID d'hôtel '{hotel_id}' existe déjà.")

        hotel = Hotel(hotel_id=hotel_id, name=hotel_name)
        session.add(hotel)
        log_activity(session, "hotel.created", f"Hôtel créé: {hotel_id}", hotel_id, performed_by, {"name": hotel_name})
        session.commit()
        session.refresh(hotel)

    # Crée le répertoire persistant
    get_hotel_dir(hotel_id)
    return HotelOut(hotel_id=hotel.hotel_id, name=hotel.name, is_active=hotel.is_active, created_at=hotel.created_at)

@app.get("/hotels", tags=["Hotel Management"], response_model=List[HotelOut])
def get_all_hotels(include_inactive: bool = Query(False)):
    with Session(engine) as session:
        statement = select(Hotel)
        if not include_inactive:
            statement = statement.where(Hotel.is_active == True)
        hotels = session.exec(statement.order_by(Hotel.created_at.desc())).all()
        return [HotelOut(hotel_id=h.hotel_id, name=h.name, is_active=h.is_active, created_at=h.created_at) for h in hotels]

@app.delete("/hotels/{hotel_id}", tags=["Hotel Management"])
def disable_hotel(hotel_id: str, performed_by: str = Query("system", alias="actor")):
    hotel_id = decode_hotel_id(hotel_id)
    with Session(engine) as session:
        hotel = session.exec(select(Hotel).where(Hotel.hotel_id == hotel_id)).first()
        if not hotel:
            raise HTTPException(status_code=404, detail="Hôtel non trouvé.")
        if not hotel.is_active:
            return {"status": "noop", "message": "L'hôtel est déjà désactivé."}
        hotel.is_active = False
        log_activity(session, "hotel.disabled", f"Hôtel désactivé: {hotel_id}", hotel_id, performed_by)
        session.add(hotel)
        session.commit()
    return {"status": "ok", "message": f"Hôtel '{hotel_id}' désactivé (soft delete)."}

# --- 8. UPLOADS & DONNÉES ---
@app.post('/upload/excel', tags=["Uploads"])
async def upload_excel(hotel_id: str = Query(...), file: UploadFile = File(...)):
    hotel_id = decode_hotel_id(hotel_id)
    hotel_dir = get_hotel_dir(hotel_id)

    if not file.filename.lower().endswith(('.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="Format non supporté. Utilisez .xlsx ou .csv")

    with Session(engine) as session:
        hotel = session.exec(select(Hotel).where(Hotel.hotel_id == hotel_id)).first()
        if not hotel:
            raise HTTPException(status_code=404, detail="Hôtel introuvable. Veuillez le créer avant l'upload.")
        if not hotel.is_active:
            raise HTTPException(status_code=423, detail="Hôtel désactivé. Réactivez-le avant l'upload.")

    try:
        content = await file.read()
        logger.info(f"Upload Excel/CSV pour {hotel_id}, taille: {len(content)} bytes")

        if file.filename.lower().endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(content), header=None)
        else:
            df = pd.read_csv(io.BytesIO(content), header=None, encoding='utf-8', sep=';')

        parsed = parse_sheet_to_structure(df)
        out_path = os.path.join(hotel_dir, f'{hotel_id}_data.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)

        with Session(engine) as session:
            log_activity(
                session,
                activity_type="data.uploaded",
                description=f"Données planning importées pour {hotel_id}",
                hotel_id=hotel_id,
                details={
                    "rooms_found": len(parsed.get('rooms', {})),
                    "dates_processed": len(parsed.get('dates_processed', [])),
                    "source": parsed.get('report_generated_at')
                },
            )
            session.commit()

        return {
            'status': 'ok',
            'hotel_id': hotel_id,
            'rooms_found': len(parsed.get('rooms', {})),
            'dates_processed': len(parsed.get('dates_processed', [])),
            'source_info': parsed.get('report_generated_at', 'Source inconnue')
        }

    except Exception as e:
        logger.error(f"Erreur traitement fichier pour {hotel_id}: {str(e)}", exc_info=True)
        with Session(engine) as session:
            log_activity(session, "data.upload_failed", f"Echec import données pour {hotel_id}", hotel_id, details={"error": str(e)})
            session.commit()
        raise HTTPException(status_code=500, detail=f"Erreur de traitement: {str(e)}")

@app.post('/upload/config', tags=["Uploads"])
async def upload_config(hotel_id: str = Query(...), file: UploadFile = File(...)):
    hotel_id = decode_hotel_id(hotel_id)
    hotel_dir = get_hotel_dir(hotel_id)

    try:
        content = await file.read()
        logger.info(f"Upload config pour {hotel_id}, taille: {len(content)} bytes")

        try:
            parsed = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Fichier JSON invalide: {str(e)}")

        file_hotel_id = parsed.get('hotel_id', '').lower().strip()
        if file_hotel_id and file_hotel_id != hotel_id:
            logger.warning(f"Incohérence ID: fichier={file_hotel_id}, paramètre={hotel_id}")

        serialized = json.dumps(parsed, ensure_ascii=False, indent=2)

        # Sauvegarde disque
        config_path = os.path.join(hotel_dir, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(serialized)

        # Sauvegarde DB
        with Session(engine) as session:
            existing = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)).first()
            if existing:
                existing.config_json = serialized
                existing.updated_at = datetime.utcnow()
            else:
                session.add(HotelConfig(hotel_id=hotel_id, config_json=serialized, updated_at=datetime.utcnow()))
            log_activity(session, "config.uploaded", f"Configuration importée pour {hotel_id}", hotel_id, details={"keys": list(parsed.keys())[:10]})
            session.commit()

        return {
            'status': 'ok',
            'hotel_id': hotel_id,
            'partners_count': len(parsed.get('partners', {})),
            'has_display_order': 'displayOrder' in parsed
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur sauvegarde config pour {hotel_id}: {str(e)}", exc_info=True)
        with Session(engine) as session:
            log_activity(session, "config.upload_failed", f"Echec import configuration pour {hotel_id}", hotel_id, details={"error": str(e)})
            session.commit()
        raise HTTPException(status_code=500, detail=f"Erreur de sauvegarde de la config: {str(e)}")

# --- 9. RÉCUPÉRATION DES DONNÉES ---
@app.get('/data', tags=["Data"])
def get_data(hotel_id: str = Query(...)):
    hotel_id = decode_hotel_id(hotel_id)
    hotel_dir = get_hotel_dir(hotel_id)
    path = os.path.join(hotel_dir, f'{hotel_id}_data.json')
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Données de planning introuvables pour '{hotel_id}'. Veuillez d'abord uploader un fichier Excel.")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Erreur lecture données pour {hotel_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur de lecture des données: {str(e)}")

@app.get('/config', tags=["Data"])
def get_config(hotel_id: str = Query(...)):
    hotel_id = decode_hotel_id(hotel_id)
    with Session(engine) as session:
        cfg = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)).first()
        if not cfg:
            # fallback disque si config.json existe
            hotel_dir = get_hotel_dir(hotel_id)
            cfg_path = os.path.join(hotel_dir, "config.json")
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        parsed = json.load(f)
                    return parsed
                except Exception:
                    pass
            raise HTTPException(status_code=404, detail=f"Configuration introuvable pour '{hotel_id}'. Veuillez uploader un JSON.")
        try:
            config_data = json.loads(cfg.config_json)
            config_data.setdefault("_meta", {})
            config_data["_meta"].update({
                "hotel_id": hotel_id,
                "updated_at": cfg.updated_at.isoformat() if hasattr(cfg, "updated_at") and cfg.updated_at else None,
            })
            return config_data
        except Exception as e:
            logger.error(f"Erreur parsing config pour {hotel_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Erreur de lecture de la configuration: {str(e)}")

# --- 10. PLANS PAR PARTENAIRE ---
@app.get("/plans/partner", tags=["Plans"])
def get_plans_by_partner(hotel_id: str = Query(...), partner_name: str = Query(...), room_type: str = Query(...)):
    try:
        hotel_id = decode_hotel_id(hotel_id)
        hotel_data = get_data(hotel_id)
        hotel_config = get_config(hotel_id)
        room_data = hotel_data.get("rooms", {}).get(room_type)
        if not room_data:
            raise HTTPException(status_code=404, detail=f"Chambre '{room_type}' introuvable")
        partner_info = hotel_config.get("partners", {}).get(partner_name, {})
        partner_codes = partner_info.get("codes", [])
        if not partner_name or not partner_info:
            all_plans = list(room_data.get("plans", {}).keys())
            return {"hotel_id": hotel_id, "partner_name": partner_name or "Direct", "room_type": room_type, "plans": all_plans, "plans_count": len(all_plans)}
        compatible_plans = []
        all_plans = room_data.get("plans", {})
        for plan_name in all_plans.keys():
            if any(code.lower() in plan_name.lower() for code in partner_codes):
                compatible_plans.append(plan_name)
        if not compatible_plans:
            compatible_plans = list(all_plans.keys())
        return {
            "hotel_id": hotel_id,
            "partner_name": partner_name,
            "room_type": room_type,
            "plans": compatible_plans,
            "plans_count": len(compatible_plans),
            "partner_commission": partner_info.get("commission", 0),
            "partner_discount": partner_info.get("defaultDiscount", {}).get("percentage", 0)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération plans pour {hotel_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des plans: {str(e)}")

# --- 11. SIMULATION ---
@app.post("/simulate", tags=["Simulation"])
async def simulate(request: SimulateIn):
    try:
        request.hotel_id = decode_hotel_id(request.hotel_id)
        dstart = datetime.strptime(request.start, '%Y-%m-%d').date()
        dend = datetime.strptime(request.end, '%Y-%m-%d').date()
        if dstart >= dend:
            raise HTTPException(status_code=400, detail="La date de début doit être avant la date de fin")

        hotel_data_full = get_data(request.hotel_id)
        hotel_data = hotel_data_full.get("rooms", {})
        hotel_config = get_config(request.hotel_id)

        room_data = hotel_data.get(request.room)
        if not room_data:
            raise HTTPException(status_code=404, detail=f"Chambre '{request.room}' introuvable.")

        plan_key = request.plan
        plan_data = room_data.get("plans", {}).get(plan_key)
        partner_info = hotel_config.get("partners", {}).get(request.partner_name, {})

        if not plan_data and partner_info and request.partner_name:
            partner_codes = partner_info.get("codes", [])
            for p_name, p_data in room_data.get("plans", {}).items():
                if any(code.lower() in p_name.lower() for code in partner_codes):
                    plan_key, plan_data = p_name, p_data
                    break

        if not plan_data:
            available_plans = list(room_data.get("plans", {}).keys())
            raise HTTPException(status_code=404, detail=f"Plan tarifaire '{request.plan}' introuvable. Plans disponibles: {available_plans[:10]}")

        commission_rate = partner_info.get("commission", 0) / 100.0 if request.apply_commission else 0.0
        discount_info = partner_info.get("defaultDiscount", {})
        partner_discount_rate = discount_info.get("percentage", 0) / 100.0 if request.apply_partner_discount else 0.0
        promo_discount_rate = request.promo_discount / 100.0

        apply_partner_discount = request.apply_partner_discount
        if apply_partner_discount and discount_info.get("excludePlansContaining"):
            exclude_keywords = discount_info.get("excludePlansContaining", [])
            if any(kw.lower() in plan_key.lower() for kw in exclude_keywords):
                apply_partner_discount = False
                partner_discount_rate = 0.0

        results = []
        current_date = dstart
        jours_semaine = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]

        while current_date < dend:
            date_key = current_date.strftime("%Y-%m-%d")
            gross_price = plan_data.get(date_key)
            stock = room_data.get("stock", {}).get(date_key, 0)

            price_after_partner = gross_price
            if gross_price is not None and apply_partner_discount and partner_discount_rate > 0:
                price_after_partner = gross_price * (1 - partner_discount_rate)

            price_after_promo = price_after_partner
            if gross_price is not None and promo_discount_rate > 0:
                price_after_promo = price_after_partner * (1 - promo_discount_rate)

            commission = price_after_promo * commission_rate if price_after_promo is not None else 0
            net_price = price_after_promo - commission if price_after_promo is not None else None

            availability = "Disponible" if stock > 0 else "Complet"
            date_display = f"{jours_semaine[current_date.weekday()]} {current_date.strftime('%d/%m')}"

            results.append({
                "date": date_key,
                "date_display": date_display,
                "stock": stock,
                "gross_price": gross_price,
                "price_after_partner_discount": price_after_partner,
                "price_after_promo": price_after_promo,
                "commission": commission,
                "net_price": net_price,
                "availability": availability
            })
            current_date += timedelta(days=1)

        valid_results = [r for r in results if r.get("gross_price") is not None]
        subtotal_brut = sum(r.get("gross_price") or 0 for r in valid_results)
        total_partner_discount = sum((r.get("gross_price") or 0) - (r.get("price_after_partner_discount") or 0) for r in valid_results)
        total_promo_discount = sum((r.get("price_after_partner_discount") or 0) - (r.get("price_after_promo") or 0) for r in valid_results)
        total_discount = total_partner_discount + total_promo_discount
        total_commission = sum(r.get("commission") or 0 for r in valid_results)
        total_net = subtotal_brut - total_discount - total_commission

        with Session(engine) as session:
            log_activity(
                session,
                activity_type="simulation.completed",
                description=f"Simulation tarifaire réalisée pour {request.hotel_id}",
                hotel_id=request.hotel_id,
                performed_by=(request.performed_by or "system"),
                details={"room": request.room, "plan": plan_key, "partner": request.partner_name, "nights": len(results), "net_total": total_net},
            )
            session.commit()

        return {
            "simulation_info": {
                "hotel_id": request.hotel_id,
                "room": request.room,
                "plan": plan_key,
                "partner": request.partner_name,
                "partner_commission": commission_rate * 100,
                "partner_discount": partner_discount_rate * 100,
                "promo_discount": request.promo_discount,
                "apply_partner_discount": apply_partner_discount,
                "start_date": request.start,
                "end_date": request.end,
                "nights": len(results),
                "source": hotel_data_full.get("report_generated_at", "Source inconnue")
            },
            "results": results,
            "summary": {
                "subtotal_brut": subtotal_brut,
                "total_partner_discount": total_partner_discount,
                "total_promo_discount": total_promo_discount,
                "total_discount": total_discount,
                "total_commission": total_commission,
                "total_net": total_net
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur simulation pour {request.hotel_id}: {str(e)}", exc_info=True)
        with Session(engine) as session:
            log_activity(session, "simulation.failed", f"Echec simulation pour {request.hotel_id}", request.hotel_id, details={"error": str(e)})
            session.commit()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la simulation: {str(e)}")

# --- 12. DISPONIBILITÉS ---
@app.post("/availability", tags=["Availability"])
async def get_availability(request: AvailabilityRequest):
    try:
        hotel_id = decode_hotel_id(request.hotel_id)
        start_date = datetime.strptime(request.start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(request.end_date, '%Y-%m-%d').date()
        if start_date >= end_date:
            raise HTTPException(status_code=400, detail="La date de début doit être avant la date de fin")

        hotel_data_full = get_data(hotel_id)
        hotel_data = hotel_data_full.get("rooms", {})

        room_types = request.room_types if request.room_types else list(hotel_data.keys())

        dates_in_period = []
        current_date = start_date
        while current_date < end_date:
            dates_in_period.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

        availability_data = {}
        for room_name in room_types:
            if room_name in hotel_data:
                room_info = hotel_data[room_name]
                availability_data[room_name] = {}
                for date_str in dates_in_period:
                    availability_data[room_name][date_str] = room_info.get("stock", {}).get(date_str, 0)

        date_display = {}
        for date_str in dates_in_period:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            jours_semaine = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
            date_display[date_str] = f"{jours_semaine[date_obj.weekday()]} {date_obj.strftime('%d/%m')}"

        with Session(engine) as session:
            log_activity(session, "availability.requested", f"Disponibilités consultées pour {hotel_id}", hotel_id, details={"room_types": room_types, "nights": len(dates_in_period)})
            session.commit()

        return {
            "hotel_id": hotel_id,
            "period": {
                "start_date": request.start_date,
                "end_date": request.end_date,
                "dates": dates_in_period,
                "date_display": date_display
            },
            "availability": availability_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur disponibilités pour {request.hotel_id}: {str(e)}")
        with Session(engine) as session:
            log_activity(session, "availability.failed", f"Echec consultation disponibilités pour {request.hotel_id}", request.hotel_id, details={"error": str(e)})
            session.commit()
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul des disponibilités: {str(e)}")

# --- 13. EXPORT EXCEL (SAUVEGARDE + ROTATION) ---
@app.post("/export/simulation", tags=["Export"])
async def export_simulation(data: dict):
    try:
        hotel_id = decode_hotel_id(data.get("simulation_info", {}).get("hotel_id", "unknown"))
        hotel_dir = get_hotel_dir(hotel_id)

        # Feuilles
        df_detail = pd.DataFrame([
            {
                "Date": day.get("date_display", day.get("date")),
                "Prix Brut (€)": day.get("gross_price"),
                "Prix Après Remise (€)": day.get("price_after_promo"),
                "Commission (€)": day.get("commission"),
                "Prix Net (€)": day.get("net_price"),
                "Stock": day.get("stock"),
                "Disponibilité": day.get("availability")
            }
            for day in data.get("results", [])
        ])
        summary = data.get("summary", {})
        sim_info = data.get("simulation_info", {})
        df_summary = pd.DataFrame([{
            "Chambre": sim_info.get("room", ""),
            "Plan Tarifaire": sim_info.get("plan", ""),
            "Partenaire": sim_info.get("partner", "Direct"),
            "Période": f"{sim_info.get('start_date', '')} au {sim_info.get('end_date', '')}",
            "Nuits": sim_info.get("nights", 0),
            "Sous-Total Brut (€)": summary.get("subtotal_brut", 0),
            "Remises et Promos (€)": summary.get("total_discount", 0),
            "Total Commission (€)": summary.get("total_commission", 0),
            "Total Net (€)": summary.get("total_net", 0)
        }])

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_detail.to_excel(writer, sheet_name='Détail par jour', index=False)
            df_summary.to_excel(writer, sheet_name='Résumé', index=False)
        output.seek(0)

        filename = f"simulation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        save_path = os.path.join(hotel_dir, filename)
        with open(save_path, "wb") as f:
            f.write(output.getbuffer())

        # Rotation: garder seulement 10 .xlsx (ne touche pas json)
        excel_files = sorted(
            [f for f in os.listdir(hotel_dir) if f.lower().endswith(".xlsx")],
            key=lambda x: os.path.getmtime(os.path.join(hotel_dir, x)),
            reverse=True,
        )
        for old_file in excel_files[10:]:
            try:
                os.remove(os.path.join(hotel_dir, old_file))
            except Exception as e:
                logger.warning(f"Impossible de supprimer {old_file}: {e}")

        with Session(engine) as session:
            log_activity(session, "simulation.exported", "Export Excel simulation généré et sauvegardé", hotel_id, details={"filename": filename, "rows": len(df_detail)})
            session.commit()

        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Erreur export Excel: {str(e)}")
        with Session(engine) as session:
            log_activity(session, "simulation.export_failed", "Echec export Excel simulation", data.get("simulation_info", {}).get("hotel_id"), details={"error": str(e)})
            session.commit()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'export: {str(e)}")

# --- 14. ENDPOINTS FICHIERS (LISTE / DOWNLOAD / INGEST) ---
@app.get("/hotel/files", tags=["Files"])
def list_hotel_files(hotel_id: str = Query(...)):
    hotel_id = decode_hotel_id(hotel_id)
    hotel_dir = get_hotel_dir(hotel_id)
    if not os.path.exists(hotel_dir):
        raise HTTPException(404, "Aucun dossier trouvé pour cet hôtel")
    files = []
    for f in sorted(os.listdir(hotel_dir), key=lambda x: os.path.getmtime(os.path.join(hotel_dir, x)), reverse=True):
        path = os.path.join(hotel_dir, f)
        if os.path.isfile(path):
            files.append({
                "filename": f,
                "size": os.path.getsize(path),
                "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
            })
    return {"hotel_id": hotel_id, "files": files}

@app.get("/hotel/file/download", tags=["Files"])
def download_hotel_file(hotel_id: str = Query(...), filename: str = Query(...)):
    hotel_id = decode_hotel_id(hotel_id)
    hotel_dir = get_hotel_dir(hotel_id)
    safe_name = os.path.basename(filename)
    path = os.path.join(hotel_dir, safe_name)
    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    media_type, _ = mimetypes.guess_type(path)
    media_type = media_type or "application/octet-stream"
    return StreamingResponse(open(path, "rb"), media_type=media_type, headers={"Content-Disposition": f"attachment; filename={safe_name}"})

@app.post("/ingest/excel-from-disk", tags=["Files"])
def ingest_excel_from_disk(hotel_id: str = Query(...), filename: str = Query(...), performed_by: str = Query("admin-ui")):
    hotel_id = decode_hotel_id(hotel_id)
    hotel_dir = get_hotel_dir(hotel_id)
    safe_name = os.path.basename(filename)
    path = os.path.join(hotel_dir, safe_name)
    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    try:
        if safe_name.lower().endswith(".xlsx"):
            df = pd.read_excel(path, header=None)
        elif safe_name.lower().endswith(".csv"):
            with open(path, "rb") as fh:
                df = pd.read_csv(fh, header=None, encoding='utf-8', sep=';')
        else:
            raise HTTPException(status_code=400, detail="Seuls .xlsx ou .csv sont supportés.")
        parsed = parse_sheet_to_structure(df)
        out_path = os.path.join(hotel_dir, f'{hotel_id}_data.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)
        with Session(engine) as session:
            log_activity(session, "data.reingested", f"Données rechargées depuis {safe_name}", hotel_id, performed_by, {"rooms": len(parsed.get('rooms', {})), "dates": len(parsed.get('dates_processed', []))})
            session.commit()
        return {"status": "ok", "hotel_id": hotel_id, "source": safe_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur ingestion disque {hotel_id}/{safe_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Echec rechargement: {str(e)}")

@app.post("/ingest/config-from-disk", tags=["Files"])
def ingest_config_from_disk(hotel_id: str = Query(...), performed_by: str = Query("admin-ui")):
    hotel_id = decode_hotel_id(hotel_id)
    hotel_dir = get_hotel_dir(hotel_id)
    cfg_path = os.path.join(hotel_dir, "config.json")
    if not os.path.exists(cfg_path):
        raise HTTPException(status_code=404, detail="config.json introuvable dans le dossier de l'hôtel")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
        serialized = json.dumps(parsed, ensure_ascii=False, indent=2)
        with Session(engine) as session:
            existing = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)).first()
            if existing:
                existing.config_json = serialized
                existing.updated_at = datetime.utcnow()
            else:
                session.add(HotelConfig(hotel_id=hotel_id, config_json=serialized, updated_at=datetime.utcnow()))
            log_activity(session, "config.reingested", "Configuration rechargée depuis config.json", hotel_id, performed_by, {"keys": list(parsed.keys())[:10]})
            session.commit()
        return {"status": "ok", "hotel_id": hotel_id}
    except Exception as e:
        logger.error(f"Erreur reload config depuis disque: {e}")
        raise HTTPException(status_code=500, detail=f"Echec rechargement config: {str(e)}")

# --- 15. DEBUG ---
@app.get("/files/status", tags=["Debug"])
def check_files_status(hotel_id: str = Query(...)):
    hotel_id = decode_hotel_id(hotel_id)
    hotel_dir = get_hotel_dir(hotel_id)
    data_path = os.path.join(hotel_dir, f'{hotel_id}_data.json')
    config_exists = False
    with Session(engine) as session:
        config_exists = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)).first() is not None
    return {
        "hotel_id": hotel_id,
        "data_file_exists": os.path.exists(data_path),
        "config_exists": config_exists,
        "paths": {
            "hotel_dir": hotel_dir,
            "data_file_path": data_path,
            "config_path": os.path.join(hotel_dir, "config.json")
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
