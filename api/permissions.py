from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlmodel import Session
from typing import List, Dict, Any
from datetime import datetime, timedelta

from database import get_session
from models import User, Hotel, UserHotelPermission
from auth import get_current_user, get_admin_user

router = APIRouter()

@router.post("/", response_model=dict)
async def create_permission(
    request_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
    session: Session = Depends(get_session)
):
    """Crée une permission d'accès pour un utilisateur à un hôtel"""
    user_email = request_data.get("user_email")
    hotel_id = request_data.get("hotel_id")
    duration = request_data.get("duration", "1_month")
    
    if not user_email or not hotel_id:
        raise HTTPException(status_code=400, detail="Email de l'utilisateur et ID de l'hôtel sont requis")
    
    # Vérifier que l'hôtel existe
    hotel = session.exec(select(Hotel).where(Hotel.hotel_id == hotel_id)).first()
    if not hotel:
        raise HTTPException(status_code=404, detail="Hôtel non trouvé")
    
    # Calculer la date d'expiration
    expiration_date = datetime.now()
    if duration == "1_day":
        expiration_date += timedelta(days=1)
    elif duration == "7_days":
        expiration_date += timedelta(days=7)
    elif duration == "1_month":
        expiration_date += timedelta(days=30)
    elif duration == "1_year":
        expiration_date += timedelta(days=365)
    else:
        expiration_date += timedelta(days=30)  # Par défaut: 1 mois
    
    # Vérifier si une permission existe déjà
    existing_permission = session.exec(
        select(UserHotelPermission)
        .where(UserHotelPermission.user_email == user_email)
        .where(UserHotelPermission.hotel_id == hotel_id)
    ).first()
    
    if existing_permission:
        # Mettre à jour la permission existante
        existing_permission.access_expires_at = expiration_date
        session.add(existing_permission)
    else:
        # Créer une nouvelle permission
        permission = UserHotelPermission(
            user_email=user_email,
            hotel_id=hotel_id,
            access_expires_at=expiration_date
        )
        session.add(permission)
    
    session.commit()
    
    return {
        "status": "ok",
        "message": f"Permission accordée à {user_email} pour l'hôtel {hotel_id} jusqu'au {expiration_date.strftime('%Y-%m-%d')}",
        "user_email": user_email,
        "hotel_id": hotel_id,
        "expires_at": expiration_date.isoformat(),
        "duration": duration
    }

@router.get("/", response_model=List[Dict[str, Any]])
async def get_all_permissions(
    current_user: User = Depends(get_admin_user),
    session: Session = Depends(get_session)
):
    """Récupère toutes les permissions actives"""
    permissions = session.exec(
        select(UserHotelPermission)
        .where(UserHotelPermission.access_expires_at > datetime.now())
        .order_by(UserHotelPermission.created_at.desc())
    ).all()
    
    # Récupérer les noms des hôtels
    hotel_ids = list(set(perm.hotel_id for perm in permissions))
    hotels = session.exec(select(Hotel).where(Hotel.hotel_id.in_(hotel_ids))).all()
    hotel_map = {hotel.hotel_id: hotel.name for hotel in hotels}
    
    return [
        {
            "id": perm.id,
            "user_email": perm.user_email,
            "hotel_id": perm.hotel_id,
            "hotel_name": hotel_map.get(perm.hotel_id, "Inconnu"),
            "access_expires_at": perm.access_expires_at.isoformat(),
            "created_at": perm.created_at.isoformat()
        }
        for perm in permissions
    ]

@router.delete("/", response_model=dict)
async def revoke_permission(
    request_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
    session: Session = Depends(get_session)
):
    """Révoque une permission d'accès"""
    user_email = request_data.get("user_email")
    hotel_id = request_data.get("hotel_id")
    
    if not user_email or not hotel_id:
        raise HTTPException(status_code=400, detail="Email de l'utilisateur et ID de l'hôtel sont requis")
    
    permission = session.exec(
        select(UserHotelPermission)
        .where(UserHotelPermission.user_email == user_email)
        .where(UserHotelPermission.hotel_id == hotel_id)
    ).first()
    
    if not permission:
        raise HTTPException(status_code=404, detail="Permission non trouvée")
    
    session.delete(permission)
    session.commit()
    
    return {
        "status": "ok",
        "message": f"Permission révoquée pour {user_email} à l'hôtel {hotel_id}"
    }

@router.get("/user/{user_email}", response_model=List[Dict[str, Any]])
async def get_user_permissions(
    user_email: str,
    current_user: User = Depends(get_admin_user),
    session: Session = Depends(get_session)
):
    """Récupère toutes les permissions d'un utilisateur spécifique"""
    permissions = session.exec(
        select(UserHotelPermission)
        .where(UserHotelPermission.user_email == user_email)
        .where(UserHotelPermission.access_expires_at > datetime.now())
        .order_by(UserHotelPermission.access_expires_at.desc())
    ).all()
    
    # Récupérer les noms des hôtels
    hotel_ids = list(set(perm.hotel_id for perm in permissions))
    hotels = session.exec(select(Hotel).where(Hotel.hotel_id.in_(hotel_ids))).all()
    hotel_map = {hotel.hotel_id: hotel.name for hotel in hotels}
    
    return [
        {
            "hotel_id": perm.hotel_id,
            "hotel_name": hotel_map.get(perm.hotel_id, "Inconnu"),
            "access_expires_at": perm.access_expires_at.isoformat()
        }
        for perm in permissions
    ]
