import os
import io
import json
import re
import logging
import zipfile
import urllib.parse
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import Column, LargeBinary
from sqlmodel import SQLModel, Field, create_engine, Session, select, func

# --- 1. CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///local.db")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Adapte l'URL pour psycopg2
engine = create_engine(DATABASE_URL.replace("postgres://", "postgresql+psycopg2://"), echo=False)

app = FastAPI(
    title="Hotel RM API - v8.0 (Multi-Hotel)",
    description="API complète pour la gestion des données hôtelières et la simulation tarifaire."
)

# --- 2. MIDDLEWARE CORS CORRIGÉ ---
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
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Middleware de gestion d'erreurs global
@app.middleware("http")
async def catch_exceptions_middleware(request, call_next):
    try:
        response = await call_next(request)
        
        # Ajout des headers CORS pour toutes les réponses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        
        return response
    except Exception as e:
        logger.error(f"Erreur non gérée: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erreur interne du serveur"},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )

# Gestion explicite des requêtes OPTIONS pour CORS preflight
@app.options("/{rest_of_path:path}")
async def preflight_handler(request, rest_of_path: str):
    return JSONResponse(
        content={"status": "OK"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400"
        }
    )

# --- 3. FONCTIONS UTILITAIRES ---
def decode_hotel_id(hotel_id: str) -> str:
    """Décode les IDs d'hôtel avec des caractères encodés"""
    return urllib.parse.unquote(hotel_id).lower().strip()

def safe_int(val) -> int:
    """Tente de convertir une valeur en entier. Gère les 'X' et formats spéciaux."""
    if pd.isna(val) or val is None:
        return 0
    
    try:
        if isinstance(val, str):
            val = val.strip().upper()
            if val == 'X' or val == 'N/A' or val == '-' or val == '':
                return 0
            # Extraction des chiffres seulement
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
    """Enregistre une activité dans l'historique centralisé."""
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


async def process_excel_file(session: Session, hotel_id: str, file_content: bytes, filename: str):
    if not filename.lower().endswith(('.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="Format non supporté. Utilisez .xlsx ou .csv")

    hotel = session.exec(select(Hotel).where(Hotel.hotel_id == hotel_id)).first()
    if not hotel:
        raise HTTPException(status_code=404, detail="Hôtel introuvable. Veuillez le créer avant l'upload.")
    if not hotel.is_active:
        raise HTTPException(status_code=423, detail="Hôtel désactivé. Réactivez-le avant l'upload.")

    try:
        logger.info(f"Upload Excel/CSV pour {hotel_id}, taille: {len(file_content)} bytes")

        if filename.lower().endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(file_content), header=None)
        else:
            df = pd.read_csv(io.BytesIO(file_content), header=None, encoding='utf-8', sep=';')

        parsed = parse_sheet_to_structure(df)
        out_path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')

        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)

        logger.info(f"Données sauvegardées pour {hotel_id}: {len(parsed.get('rooms', {}))} chambres")

        report_label = parsed.get('report_generated_at')
        report_timestamp = None
        if report_label:
            try:
                parsed_timestamp = pd.to_datetime(report_label, dayfirst=True, errors='coerce')
                if not pd.isna(parsed_timestamp):
                    report_timestamp = parsed_timestamp.to_pydatetime()
            except Exception:
                report_timestamp = None

        extension = os.path.splitext(filename)[1].lower()
        content_type_map = {
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.csv': 'text/csv',
        }
        upload_entry = UploadedFile(
            hotel_id=hotel_id,
            filename=filename,
            content_type=content_type_map.get(extension, 'application/octet-stream'),
            file_size=len(file_content),
            report_generated_at=report_timestamp,
            report_generated_label=report_label,
            stored_path=out_path,
            data=file_content,
        )
        session.add(upload_entry)
        session.flush()

        log_activity(
            session,
            activity_type="data.uploaded",
            description=f"Données planning importées pour {hotel_id}",
            hotel_id=hotel_id,
            details={
                "rooms_found": len(parsed.get('rooms', {})),
                "dates_processed": len(parsed.get('dates_processed', [])),
                "upload_id": upload_entry.id,
                "report_generated_at": report_timestamp.isoformat() if report_timestamp else report_label,
            },
        )
        session.commit()

        return {
            'status': 'ok',
            'hotel_id': hotel_id,
            'rooms_found': len(parsed.get('rooms', {})),
            'dates_processed': len(parsed.get('dates_processed', [])),
            'source_info': report_label or 'Source inconnue',
            'upload_id': upload_entry.id,
            'report_generated_at': report_timestamp.isoformat() if report_timestamp else None,
        }

    except Exception as e:
        logger.error(f"Erreur traitement fichier pour {hotel_id}: {str(e)}", exc_info=True)
        log_activity(
            session,
            activity_type="data.upload_failed",
            description=f"Echec import données pour {hotel_id}",
            hotel_id=hotel_id,
            details={"error": str(e)},
        )
        session.commit()
        raise HTTPException(status_code=500, detail=f"Erreur de traitement: {str(e)}")


async def process_json_config(session: Session, hotel_id: str, file_content: bytes):
    try:
        logger.info(f"Upload config pour {hotel_id}, taille: {len(file_content)} bytes")

        # Validation du contenu JSON
        try:
            parsed = json.loads(file_content.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"JSON invalide pour {hotel_id}: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Fichier JSON invalide: {str(e)}")

        # Validation de la structure
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="Le fichier JSON doit être un objet")

        # Vérification optionnelle de l'ID d'hôtel
        file_hotel_id = parsed.get('hotel_id', '').lower().strip()
        if file_hotel_id and file_hotel_id != hotel_id:
            logger.warning(f"Incohérence ID: fichier={file_hotel_id}, paramètre={hotel_id}")

        serialized = json.dumps(parsed, ensure_ascii=False, indent=2)

        existing = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)).first()
        if existing:
            existing.config_json = serialized
            existing.updated_at = datetime.utcnow()
        else:
            session.add(
                HotelConfig(
                    hotel_id=hotel_id,
                    config_json=serialized,
                    updated_at=datetime.utcnow(),
                )
            )
        log_activity(
            session,
            activity_type="config.uploaded",
            description=f"Configuration importée pour {hotel_id}",
            hotel_id=hotel_id,
            details={"keys": list(parsed.keys())[:10]},
        )
        session.commit()

        logger.info(f"Config sauvegardée pour {hotel_id}: {len(parsed.get('partners', {}))} partenaires")

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
        log_activity(
            session,
            activity_type="config.upload_failed",
            description=f"Echec import configuration pour {hotel_id}",
            hotel_id=hotel_id,
            details={"error": str(e)},
        )
        session.commit()
        raise HTTPException(status_code=500, detail=f"Erreur de sauvegarde de la config: {str(e)}")

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


class UploadedFile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hotel_id: str = Field(index=True)
    filename: str
    content_type: Optional[str] = Field(default=None)
    file_size: int = Field(default=0)
    uploaded_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    report_generated_at: Optional[datetime] = Field(default=None, index=True)
    report_generated_label: Optional[str] = Field(default=None)
    stored_path: Optional[str] = Field(default=None)
    data: bytes = Field(sa_column=Column(LargeBinary), default=b"")


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


class UploadedFileOut(BaseModel):
    id: int
    hotel_id: str
    filename: str
    content_type: Optional[str]
    file_size: int
    uploaded_at: datetime
    report_generated_at: Optional[datetime]
    report_generated_label: Optional[str]

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
    performed_by: Optional[str] = PydanticField(default="system")


class AvailabilityRequest(BaseModel):
    hotel_id: str
    start_date: str
    end_date: str
    room_types: List[str] = PydanticField(default_factory=list)
    performed_by: Optional[str] = PydanticField(default="system")

# --- 5. ÉVÉNEMENTS DE DÉMARRAGE ---
@app.on_event('startup')
def on_startup():
    SQLModel.metadata.create_all(engine)
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info("Application démarrée avec succès")

# --- 6. FONCTIONS DE PARSING ---
def parse_sheet_to_structure(df: pd.DataFrame) -> dict:
    """
    Nouveau parser adapté à la structure réelle des fichiers CSV
    """
    hotel_data = {}
    if df.shape[0] < 1: 
        return {}

    # Récupération de la source (cellule A1)
    source_info = str(df.iloc[0, 0]) if df.shape[0] > 0 and df.shape[1] > 0 else "Source inconnue"

    # Détection des colonnes de date (première ligne)
    header_row = df.iloc[0].tolist()
    date_cols = []
    
    for j, col_value in enumerate(header_row):
        if pd.isna(col_value) or j < 3:
            continue
            
        date_str = None
        try:
            # Gestion des dates au format français DD/MM/YYYY
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

    # Parcours des lignes de données
    current_room = None
    current_stock_data = {}
    
    for i in range(1, df.shape[0]):
        row = df.iloc[i].tolist()
        
        # Gestion des cellules vides
        if all(pd.isna(cell) for cell in row[:3]):
            continue
            
        # Détection du nom de la chambre (colonne 0)
        if pd.notna(row[0]) and str(row[0]).strip():
            current_room = str(row[0]).strip()
            
        if not current_room:
            continue
            
        # Initialisation de la structure pour cette chambre
        if current_room not in hotel_data:
            hotel_data[current_room] = {'stock': {}, 'plans': {}}
            
        # Détection du type de ligne
        descriptor = str(row[2]).strip().lower() if pd.notna(row[2]) else ""
        
        if 'left for sale' in descriptor:
            # Ligne de stock
            current_stock_data = {}
            for dc in date_cols:
                if dc['index'] < len(row):
                    stock_value = row[dc['index']]
                    current_stock_data[dc['date']] = safe_int(stock_value)
            
            hotel_data[current_room]['stock'] = current_stock_data
            
        elif 'price' in descriptor and current_stock_data:
            # Ligne de prix
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

# --- 7. ENDPOINTS DE L'API ---

@app.get("/", tags=["Status"])
def read_root(): 
    return {
        "status": "Hotel RM API v8.0 is running", 
        "timestamp": datetime.now().isoformat(),
        "cors_enabled": True
    }

@app.get("/health", tags=["Status"])
def health_check():
    """Endpoint de vérification de la santé de l'API"""
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
        "version": "9.0",
        "latency_ms": round(duration_ms, 2),
        "metrics": metrics,
        "cors": "enabled",
    }


@app.get("/monitor/health", tags=["Monitoring"])
def monitor_health():
    started = datetime.utcnow()
    db_status = "unknown"
    db_file_count = 0
    db_file_bytes = 0
    with Session(engine) as session:
        metrics = get_system_metrics(session)
        db_status = "healthy"
        uploaded_stats = session.exec(
            select(
                func.count(UploadedFile.id),
                func.coalesce(func.sum(func.length(UploadedFile.data)), 0),
            )
        ).one()
        if isinstance(uploaded_stats, tuple):
            db_file_count, db_file_bytes = uploaded_stats
        else:
            db_file_count = uploaded_stats[0]
            db_file_bytes = uploaded_stats[1]

    data_files = [f for f in os.listdir(DATA_DIR) if f.endswith('_data.json')]
    storage_usage = 0
    for filename in data_files:
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            storage_usage += os.path.getsize(path)

    return {
        "status": "ok",
        "generated_at": datetime.utcnow().isoformat(),
        "latency_ms": round(max((datetime.utcnow() - started).total_seconds() * 1000, 0), 2),
        "database": db_status,
        "metrics": metrics,
        "storage": {
            "files": len(data_files),
            "bytes": storage_usage,
            "database_files": db_file_count or 0,
            "database_bytes": int(db_file_bytes or 0),
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

# --- Gestion des Hôtels ---
@app.post("/hotels", tags=["Hotel Management"], response_model=HotelOut, status_code=201)
def create_hotel(payload: HotelCreate, performed_by: str = Query("system", alias="actor")):
    hotel_id = decode_hotel_id(payload.hotel_id)

    if not re.fullmatch(r"[a-z0-9-]{3,64}", hotel_id):
        raise HTTPException(
            status_code=400,
            detail="L'identifiant d'hôtel doit contenir uniquement des minuscules, chiffres ou tirets.",
        )

    hotel_name = (payload.name or "").strip() or None

    with Session(engine) as session:
        existing = session.exec(select(Hotel).where(Hotel.hotel_id == hotel_id)).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.name = hotel_name or existing.name
                log_activity(
                    session,
                    activity_type="hotel.reactivated",
                    description=f"Hôtel réactivé: {hotel_id}",
                    hotel_id=hotel_id,
                    performed_by=performed_by,
                    details={"name": existing.name},
                )
                session.commit()
                session.refresh(existing)
                logger.info(f"Hôtel réactivé: {hotel_id}")
                return HotelOut(
                    hotel_id=existing.hotel_id,
                    name=existing.name,
                    is_active=existing.is_active,
                    created_at=existing.created_at,
                )

            raise HTTPException(status_code=409, detail=f"L'ID d'hôtel '{hotel_id}' existe déjà.")

        hotel = Hotel(hotel_id=hotel_id, name=hotel_name)
        session.add(hotel)
        log_activity(
            session,
            activity_type="hotel.created",
            description=f"Hôtel créé: {hotel_id}",
            hotel_id=hotel_id,
            performed_by=performed_by,
            details={"name": hotel_name},
        )
        session.commit()
        session.refresh(hotel)
        logger.info(f"Hôtel créé: {hotel_id}")

        return HotelOut(
            hotel_id=hotel.hotel_id,
            name=hotel.name,
            is_active=hotel.is_active,
            created_at=hotel.created_at,
        )


@app.get("/hotels", tags=["Hotel Management"], response_model=List[HotelOut])
def get_all_hotels(include_inactive: bool = Query(False)):
    with Session(engine) as session:
        statement = select(Hotel)
        if not include_inactive:
            statement = statement.where(Hotel.is_active == True)

        hotels = session.exec(statement.order_by(Hotel.created_at.desc())).all()
        logger.info(f"Liste des hôtels récupérée: {len(hotels)} hôtels")

        return [
            HotelOut(
                hotel_id=h.hotel_id,
                name=h.name,
                is_active=h.is_active,
                created_at=h.created_at,
            )
            for h in hotels
        ]


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
        log_activity(
            session,
            activity_type="hotel.disabled",
            description=f"Hôtel désactivé: {hotel_id}",
            hotel_id=hotel_id,
            performed_by=performed_by,
        )
        session.add(hotel)
        session.commit()

    logger.info(f"Hôtel désactivé: {hotel_id}")
    return {"status": "ok", "message": f"Hôtel '{hotel_id}' désactivé (soft delete)."}

# --- Gestion des Fichiers ---
@app.post('/upload/data', tags=["Uploads"])
async def upload_data(hotel_id: str = Query(...), file: UploadFile = File(...)):
    hotel_id = decode_hotel_id(hotel_id)
    file_content = await file.read()

    with Session(engine) as session:
        if file.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
            return await process_excel_file(session, hotel_id, file_content, file.filename)
        elif file.filename.lower().endswith('.json'):
            return await process_json_config(session, hotel_id, file_content)
        else:
            raise HTTPException(status_code=400, detail="Format de fichier non supporté. Utilisez .xlsx, .xls ou .json")


@app.post('/upload/excel', tags=["Uploads"])
async def upload_excel(hotel_id: str = Query(...), file: UploadFile = File(...)):
    hotel_id = decode_hotel_id(hotel_id)
    with Session(engine) as session:
        return await process_excel_file(session, hotel_id, await file.read(), file.filename)


@app.post('/upload/config', tags=["Uploads"])
async def upload_config(hotel_id: str = Query(...), file: UploadFile = File(...)):
    hotel_id = decode_hotel_id(hotel_id)
    with Session(engine) as session:
        return await process_json_config(session, hotel_id, await file.read())


@app.get('/uploads/recent', tags=["Uploads"], response_model=List[UploadedFileOut])
def list_recent_uploads(hotel_id: Optional[str] = Query(default=None)):
    with Session(engine) as session:
        statement = select(UploadedFile)
        if hotel_id:
            statement = statement.where(UploadedFile.hotel_id == decode_hotel_id(hotel_id))
        ordering_key = func.coalesce(UploadedFile.report_generated_at, UploadedFile.uploaded_at)
        uploads = session.exec(
            statement.order_by(ordering_key.desc(), UploadedFile.id.desc()).limit(10)
        ).all()

    return [
        UploadedFileOut(
            id=upload.id,
            hotel_id=upload.hotel_id,
            filename=upload.filename,
            content_type=upload.content_type,
            file_size=upload.file_size,
            uploaded_at=upload.uploaded_at,
            report_generated_at=upload.report_generated_at,
            report_generated_label=upload.report_generated_label,
        )
        for upload in uploads
    ]


@app.get('/uploads/{upload_id}/download', tags=["Uploads"])
def download_upload(upload_id: int):
    with Session(engine) as session:
        upload = session.get(UploadedFile, upload_id)
        if not upload:
            raise HTTPException(status_code=404, detail="Fichier importé introuvable")

        file_bytes = bytes(upload.data or b"")
        filename = upload.filename or f"import_{upload_id}.bin"
        content_type = upload.content_type or 'application/octet-stream'

        log_activity(
            session,
            activity_type="data.downloaded",
            description=f"Téléchargement du fichier importé #{upload_id}",
            hotel_id=upload.hotel_id,
            details={
                "filename": upload.filename,
                "file_size": upload.file_size,
            },
        )
        session.commit()

    output = io.BytesIO(file_bytes)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


@app.post('/backup/immediate', tags=["Backup"])
def backup_immediate(performed_by: str = Query("system", alias="actor")):
    generated_at = datetime.utcnow()
    archive_name = f"backup_{generated_at.strftime('%Y%m%d_%H%M%S')}.zip"
    buffer = io.BytesIO()

    def sanitize(value: str) -> str:
        return re.sub(r'[^A-Za-z0-9._-]', '_', value)

    with Session(engine) as session:
        hotels = session.exec(select(Hotel)).all()
        uploads = session.exec(select(UploadedFile).order_by(UploadedFile.uploaded_at)).all()

        data_files_written = 0
        config_files_written = 0
        excel_files_written = 0
        total_bytes = 0

        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for hotel in hotels:
                data_path = os.path.join(DATA_DIR, f'{hotel.hotel_id}_data.json')
                if os.path.exists(data_path):
                    with open(data_path, 'r', encoding='utf-8') as data_file:
                        content = data_file.read()
                    archive.writestr(f"data/{hotel.hotel_id}.json", content)
                    data_files_written += 1
                    total_bytes += len(content.encode('utf-8'))

                config = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel.hotel_id)).first()
                if config:
                    archive.writestr(f"config/{hotel.hotel_id}.json", config.config_json)
                    config_files_written += 1
                    total_bytes += len(config.config_json.encode('utf-8'))

            for upload in uploads:
                if not upload.data:
                    continue
                safe_filename = sanitize(upload.filename or f"import_{upload.id}.bin")
                archive_name_for_file = f"excel/{sanitize(upload.hotel_id)}/{upload.uploaded_at.strftime('%Y%m%d_%H%M%S')}_{safe_filename}"
                archive.writestr(archive_name_for_file, upload.data)
                excel_files_written += 1
                total_bytes += len(upload.data or b"")

            metadata = {
                "generated_at": generated_at.isoformat(),
                "generated_by": performed_by,
                "counts": {
                    "hotels": len(hotels),
                    "data_files": data_files_written,
                    "config_files": config_files_written,
                    "excel_files": excel_files_written,
                },
                "totals": {
                    "bytes": total_bytes,
                },
                "recent_uploads": [
                    {
                        "id": upload.id,
                        "hotel_id": upload.hotel_id,
                        "filename": upload.filename,
                        "uploaded_at": upload.uploaded_at.isoformat(),
                        "report_generated_at": upload.report_generated_at.isoformat() if upload.report_generated_at else None,
                    }
                    for upload in sorted(uploads, key=lambda item: item.report_generated_at or item.uploaded_at or generated_at)[-10:]
                ],
            }
            archive.writestr('metadata.json', json.dumps(metadata, indent=2, ensure_ascii=False))

        log_activity(
            session,
            activity_type="backup.created",
            description="Sauvegarde complète générée",
            performed_by=performed_by,
            details={
                "filename": archive_name,
                "data_files": data_files_written,
                "config_files": config_files_written,
                "excel_files": excel_files_written,
                "bytes": total_bytes,
            },
        )
        session.commit()

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type='application/zip',
        headers={"Content-Disposition": f"attachment; filename=\"{archive_name}\""},
    )

# --- Récupération des Données ---
@app.get('/data', tags=["Data"])
def get_data(hotel_id: str = Query(...)):
    hotel_id = decode_hotel_id(hotel_id)
    path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')
    
    if not os.path.exists(path): 
        raise HTTPException(
            status_code=404, 
            detail=f"Données de planning introuvables pour '{hotel_id}'. Veuillez d'abord uploader un fichier Excel."
        )
    
    try:
        with open(path, 'r', encoding='utf-8') as f: 
            data = json.load(f)
        logger.info(f"Données chargées pour {hotel_id}")
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
            raise HTTPException(
                status_code=404, 
                detail=f"Configuration introuvable pour '{hotel_id}'. Veuillez d'abord uploader un fichier JSON de configuration."
            )
        
        try:
            config_data = json.loads(cfg.config_json)
            config_data.setdefault("_meta", {})
            config_data["_meta"].update({
                "hotel_id": hotel_id,
                "updated_at": cfg.updated_at.isoformat() if hasattr(cfg, "updated_at") and cfg.updated_at else None,
            })
            logger.info(f"Config chargée pour {hotel_id}")
            return config_data
        except Exception as e:
            logger.error(f"Erreur parsing config pour {hotel_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Erreur de lecture de la configuration: {str(e)}")

# --- NOUVEAU: Plans par partenaire ---
@app.get("/plans/partner", tags=["Plans"])
def get_plans_by_partner(hotel_id: str = Query(...), partner_name: str = Query(...), room_type: str = Query(...)):
    """Récupère les plans tarifaires disponibles pour un partenaire et une chambre spécifiques"""
    try:
        hotel_id = decode_hotel_id(hotel_id)
        
        # Charger les données
        hotel_data = get_data(hotel_id)
        hotel_config = get_config(hotel_id)
        
        # Vérifier que la chambre existe
        room_data = hotel_data.get("rooms", {}).get(room_type)
        if not room_data:
            raise HTTPException(status_code=404, detail=f"Chambre '{room_type}' introuvable")
        
        # Récupérer les informations du partenaire
        partner_info = hotel_config.get("partners", {}).get(partner_name, {})
        partner_codes = partner_info.get("codes", [])
        
        # Si pas de partenaire spécifique, retourner tous les plans
        if not partner_name or not partner_info:
            all_plans = list(room_data.get("plans", {}).keys())
            return {
                "hotel_id": hotel_id,
                "partner_name": partner_name or "Direct",
                "room_type": room_type,
                "plans": all_plans,
                "plans_count": len(all_plans)
            }
        
        # Filtrer les plans selon les codes du partenaire
        compatible_plans = []
        all_plans = room_data.get("plans", {})
        
        for plan_name in all_plans.keys():
            # Vérifier si le plan correspond aux codes du partenaire
            if any(code.lower() in plan_name.lower() for code in partner_codes):
                compatible_plans.append(plan_name)
        
        # Si aucun plan compatible, retourner tous les plans avec un avertissement
        if not compatible_plans:
            logger.warning(f"Aucun plan compatible trouvé pour {partner_name} dans {room_type}")
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

# --- Simulation ---
@app.post("/simulate", tags=["Simulation"])
async def simulate(request: SimulateIn):
    """Version améliorée avec gestion complète des remises partenaires"""
    try:
        request.hotel_id = decode_hotel_id(request.hotel_id)
        logger.info(f"Simulation demandée pour {request.hotel_id}, chambre: {request.room}, plan: {request.plan}")

        # Validation des dates
        dstart = datetime.strptime(request.start, '%Y-%m-%d').date()
        dend = datetime.strptime(request.end, '%Y-%m-%d').date()
        
        if dstart >= dend:
            raise HTTPException(status_code=400, detail="La date de début doit être avant la date de fin")

        # Récupération des données
        hotel_data_full = get_data(request.hotel_id)
        hotel_data = hotel_data_full.get("rooms", {})
        hotel_config = get_config(request.hotel_id)
        
        room_data = hotel_data.get(request.room)
        if not room_data:
            raise HTTPException(status_code=404, detail=f"Chambre '{request.room}' introuvable.")
        
        # Recherche du plan tarifaire
        plan_key = request.plan
        plan_data = room_data.get("plans", {}).get(plan_key)
        partner_info = hotel_config.get("partners", {}).get(request.partner_name, {})
        
        # Si plan non trouvé directement, chercher via les codes partenaires
        if not plan_data and partner_info and request.partner_name:
            partner_codes = partner_info.get("codes", [])
            for p_name, p_data in room_data.get("plans", {}).items():
                if any(code.lower() in p_name.lower() for code in partner_codes):
                    plan_key, plan_data = p_name, p_data
                    logger.info(f"Plan trouvé via partenaire: {p_name}")
                    break
        
        if not plan_data:
            available_plans = list(room_data.get("plans", {}).keys())
            raise HTTPException(
                status_code=404, 
                detail=f"Plan tarifaire '{request.plan}' introuvable. Plans disponibles: {available_plans[:10]}"
            )

        # Configuration des calculs
        commission_rate = partner_info.get("commission", 0) / 100.0 if request.apply_commission else 0.0
        discount_info = partner_info.get("defaultDiscount", {})
        partner_discount_rate = discount_info.get("percentage", 0) / 100.0 if request.apply_partner_discount else 0.0
        promo_discount_rate = request.promo_discount / 100.0
        
        # Vérification si le plan est exclu de la remise partenaire
        apply_partner_discount = request.apply_partner_discount
        if apply_partner_discount and discount_info.get("excludePlansContaining"):
            exclude_keywords = discount_info.get("excludePlansContaining", [])
            if any(kw.lower() in plan_key.lower() for kw in exclude_keywords):
                apply_partner_discount = False
                partner_discount_rate = 0.0
                logger.info(f"Remise partenaire exclue pour le plan: {plan_key}")

        # Calculs par date
        results = []
        current_date = dstart
        
        while current_date < dend:
            date_key = current_date.strftime("%Y-%m-%d")
            gross_price = plan_data.get(date_key)
            stock = room_data.get("stock", {}).get(date_key, 0)
            
            # Application des remises en cascade (d'abord remise partenaire, puis promo)
            price_after_partner_discount = gross_price
            if gross_price is not None and apply_partner_discount and partner_discount_rate > 0:
                price_after_partner_discount = gross_price * (1 - partner_discount_rate)
            
            price_after_promo = price_after_partner_discount
            if gross_price is not None and promo_discount_rate > 0:
                price_after_promo = price_after_partner_discount * (1 - promo_discount_rate)
            
            # Calcul de la commission (sur le prix après toutes les remises)
            commission = price_after_promo * commission_rate if price_after_promo is not None else 0
            net_price = price_after_promo - commission if price_after_promo is not None else None

            # Détermination de la disponibilité
            availability = "Disponible" if stock > 0 else "Complet"
            
            # Format de date avec jour de la semaine en français
            jours_semaine = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
            date_display = f"{jours_semaine[current_date.weekday()]} {current_date.strftime('%d/%m')}"
            
            results.append({
                "date": date_key,
                "date_display": date_display,
                "stock": stock,
                "gross_price": gross_price,
                "price_after_partner_discount": price_after_partner_discount,
                "price_after_promo": price_after_promo,
                "commission": commission,
                "net_price": net_price,
                "availability": availability
            })
            current_date += timedelta(days=1)

        # Calcul des totaux
        valid_results = [r for r in results if r.get("gross_price") is not None]
        subtotal_brut = sum(r.get("gross_price") or 0 for r in valid_results)
        total_partner_discount = sum((r.get("gross_price") or 0) - (r.get("price_after_partner_discount") or 0) for r in valid_results)
        total_promo_discount = sum((r.get("price_after_partner_discount") or 0) - (r.get("price_after_promo") or 0) for r in valid_results)
        total_discount = total_partner_discount + total_promo_discount
        total_commission = sum(r.get("commission") or 0 for r in valid_results)
        total_net = subtotal_brut - total_discount - total_commission

        logger.info(f"Simulation terminée pour {request.hotel_id}: {len(results)} jours, total net: {total_net}")

        with Session(engine) as session:
            log_activity(
                session,
                activity_type="simulation.completed",
                description=f"Simulation tarifaire réalisée pour {request.hotel_id}",
                hotel_id=request.hotel_id,
                performed_by=(request.performed_by or "system"),
                details={
                    "room": request.room,
                    "plan": plan_key,
                    "partner": request.partner_name,
                    "nights": len(results),
                    "net_total": total_net,
                },
            )
            session.commit()

        response = {
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

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur simulation pour {request.hotel_id}: {str(e)}", exc_info=True)
        with Session(engine) as session:
            log_activity(
                session,
                activity_type="simulation.failed",
                description=f"Echec simulation pour {request.hotel_id}",
                hotel_id=request.hotel_id,
                performed_by=(request.performed_by or "system"),
                details={"error": str(e)},
            )
            session.commit()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la simulation: {str(e)}")

# --- NOUVEAU: Disponibilités ---
@app.post("/availability", tags=["Availability"])
async def get_availability(request: AvailabilityRequest):
    """Récupère les disponibilités pour une période donnée"""
    try:
        hotel_id = decode_hotel_id(request.hotel_id)
        
        # Validation des dates
        start_date = datetime.strptime(request.start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(request.end_date, '%Y-%m-%d').date()
        
        if start_date >= end_date:
            raise HTTPException(status_code=400, detail="La date de début doit être avant la date de fin")

        # Charger les données
        hotel_data_full = get_data(hotel_id)
        hotel_data = hotel_data_full.get("rooms", {})
        
        # Filtrer les chambres si spécifié
        room_types = request.room_types if request.room_types else list(hotel_data.keys())
        
        # Générer toutes les dates de la période
        dates_in_period = []
        current_date = start_date
        while current_date < end_date:
            dates_in_period.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)
        
        # Préparer les données de disponibilité
        availability_data = {}
        for room_name in room_types:
            if room_name in hotel_data:
                room_info = hotel_data[room_name]
                availability_data[room_name] = {}
                for date_str in dates_in_period:
                    availability_data[room_name][date_str] = room_info.get("stock", {}).get(date_str, 0)
        
        # Format des dates pour l'affichage
        date_display = {}
        for date_str in dates_in_period:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            jours_semaine = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
            date_display[date_str] = f"{jours_semaine[date_obj.weekday()]} {date_obj.strftime('%d/%m')}"
        
        response = {
            "hotel_id": hotel_id,
            "period": {
                "start_date": request.start_date,
                "end_date": request.end_date,
                "dates": dates_in_period,
                "date_display": date_display
            },
            "availability": availability_data
        }

        with Session(engine) as session:
            log_activity(
                session,
                activity_type="availability.requested",
                description=f"Disponibilités consultées pour {hotel_id}",
                hotel_id=hotel_id,
                performed_by=(request.performed_by or "system"),
                details={
                    "room_types": room_types,
                    "nights": len(dates_in_period),
                },
            )
            session.commit()

        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur disponibilités pour {request.hotel_id}: {str(e)}")
        with Session(engine) as session:
            log_activity(
                session,
                activity_type="availability.failed",
                description=f"Echec consultation disponibilités pour {request.hotel_id}",
                hotel_id=request.hotel_id,
                performed_by=(request.performed_by or "system"),
                details={"error": str(e)},
            )
            session.commit()
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul des disponibilités: {str(e)}")

# --- Export Excel ---
@app.post("/export/simulation", tags=["Export"])
async def export_simulation(data: dict):
    """Exporte les résultats de simulation en format Excel"""
    try:
        output = io.BytesIO()
        
        # Création du DataFrame principal
        df_data = []
        for day in data.get("results", []):
            df_data.append({
                "Date": day.get("date_display", day.get("date")),
                "Prix Brut (€)": day.get("gross_price"),
                "Prix Après Remise (€)": day.get("price_after_promo"),
                "Commission (€)": day.get("commission"),
                "Prix Net (€)": day.get("net_price"),
                "Stock": day.get("stock"),
                "Disponibilité": day.get("availability")
            })
        
        df = pd.DataFrame(df_data)
        
        # Création du fichier Excel en mémoire
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Détail par jour', index=False)
            
            # Ajout du résumé
            summary = data.get("summary", {})
            sim_info = data.get("simulation_info", {})
            
            summary_data = {
                "Chambre": [sim_info.get("room", "")],
                "Plan Tarifaire": [sim_info.get("plan", "")],
                "Partenaire": [sim_info.get("partner", "Direct")],
                "Période": [f"{sim_info.get('start_date', '')} au {sim_info.get('end_date', '')}"],
                "Nuits": [sim_info.get("nights", 0)],
                "Sous-Total Brut (€)": [summary.get("subtotal_brut", 0)],
                "Remises et Promos (€)": [summary.get("total_discount", 0)],
                "Total Commission (€)": [summary.get("total_commission", 0)],
                "Total Net (€)": [summary.get("total_net", 0)]
            }
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Résumé', index=False)
        
        output.seek(0)

        # Retour en streaming
        filename = f"simulation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logger.info(f"Export Excel généré: {filename}")
        with Session(engine) as session:
            log_activity(
                session,
                activity_type="simulation.exported",
                description="Export Excel simulation généré",
                hotel_id=data.get("simulation_info", {}).get("hotel_id"),
                details={
                    "filename": filename,
                    "rows": len(data.get("results", [])),
                },
            )
            session.commit()
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Erreur export Excel: {str(e)}")
        with Session(engine) as session:
            log_activity(
                session,
                activity_type="simulation.export_failed",
                description="Echec export Excel simulation",
                hotel_id=data.get("simulation_info", {}).get("hotel_id"),
                details={"error": str(e)},
            )
            session.commit()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'export: {str(e)}")

# --- Debug Endpoints ---
@app.get("/files/status", tags=["Debug"])
def check_files_status(hotel_id: str = Query(...)):
    """Vérifie l'existence des fichiers pour un hôtel"""
    hotel_id = decode_hotel_id(hotel_id)
    
    data_path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')
    config_exists = False
    
    with Session(engine) as session:
        config_exists = session.exec(select(HotelConfig).where(HotelConfig.hotel_id == hotel_id)).first() is not None
    
    return {
        "hotel_id": hotel_id,
        "data_file_exists": os.path.exists(data_path),
        "config_exists": config_exists,
        "data_file_path": data_path
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))