from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlmodel import Session
import io
import json
import os
import re
import pandas as pd
from datetime import datetime, timedelta

from database import get_session
from models import User
from auth import get_current_user, check_hotel_permission

router = APIRouter()

DATA_DIR = "/app/data"

@router.post("/excel", response_model=dict)
async def upload_excel(
    hotel_id: str = Query(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Télécharge un fichier Excel/CSV pour un hôtel spécifique"""
    # Vérifier les permissions
    check_hotel_permission(hotel_id, current_user, session)
    
    if not file.filename.lower().endswith(('.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="Format non supporté. Utilisez .xlsx ou .csv")
    
    try:
        content = await file.read()
        
        if file.filename.lower().endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(content), header=None)
        else:
            df = pd.read_csv(io.BytesIO(content), header=None, encoding='utf-8', sep=';')
        
        # Utiliser la fonction de parsing existante
        parsed = parse_sheet_to_structure(df)
        out_path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')
        
        with open(out_path, 'w', encoding='utf-8') as f: 
            json.dump(parsed, f, indent=2, ensure_ascii=False)
        
        return {
            'status': 'ok', 
            'hotel_id': hotel_id, 
            'rooms_found': len(parsed.get('rooms', {})),
            'dates_processed': len(parsed.get('dates_processed', [])),
            'source_info': parsed.get('report_generated_at', 'Source inconnue')
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de traitement: {str(e)}")

@router.post("/config", response_model=dict)
async def upload_config(
    hotel_id: str = Query(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Télécharge un fichier de configuration JSON pour un hôtel spécifique"""
    # Vérifier les permissions
    check_hotel_permission(hotel_id, current_user, session)
    
    try:
        content = await file.read()
        
        # Validation du contenu JSON
        try:
            parsed = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Fichier JSON invalide: {str(e)}")
        
        # Validation de la structure
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="Le fichier JSON doit être un objet")
        
        out_path = os.path.join(DATA_DIR, f'{hotel_id}_config.json')
        
        with open(out_path, 'w', encoding='utf-8') as f: 
            json.dump(parsed, f, indent=2, ensure_ascii=False)
        
        return {
            'status': 'ok', 
            'hotel_id': hotel_id,
            'partners_count': len(parsed.get('partners', {})),
            'has_display_order': 'displayOrder' in parsed
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de sauvegarde de la config: {str(e)}")

@router.get("/data", response_model=dict)
async def get_data(
    hotel_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Récupère les données d'un hôtel spécifique"""
    # Vérifier les permissions
    check_hotel_permission(hotel_id, current_user, session)
    
    path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')
    
    if not os.path.exists(path): 
        raise HTTPException(
            status_code=404, 
            detail=f"Données de planning introuvables pour '{hotel_id}'."
        )
    
    try:
        with open(path, 'r', encoding='utf-8') as f: 
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de lecture des données: {str(e)}")

@router.get("/config", response_model=dict)
async def get_config(
    hotel_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Récupère la configuration d'un hôtel spécifique"""
    # Vérifier les permissions
    check_hotel_permission(hotel_id, current_user, session)
    
    path = os.path.join(DATA_DIR, f'{hotel_id}_config.json')
    
    if not os.path.exists(path): 
        raise HTTPException(
            status_code=404, 
            detail=f"Configuration introuvable pour '{hotel_id}'."
        )
    
    try:
        with open(path, 'r', encoding='utf-8') as f: 
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de lecture de la configuration: {str(e)}")

def parse_sheet_to_structure(df: pd.DataFrame) -> dict:
    """
    Fonction de parsing adaptée à la structure des fichiers Excel/CSV
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
                    except (ValueError, TypeError):
                        hotel_data[current_room]['plans'][plan_name][dc['date']] = None

    return {
        'report_generated_at': source_info,
        'rooms': hotel_data,
        'dates_processed': [dc['date'] for dc in date_cols]
    }

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
