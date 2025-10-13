from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List
from datetime import datetime

from database import get_session
from models import Hotel
from auth import get_current_user, check_hotel_permission, get_admin_user

router = APIRouter()

@router.post("/", response_model=dict)
async def create_hotel(
    hotel_id: str = Query(..., min_length=3),
    name: str = Query(...),
    current_user: User = Depends(get_admin_user),
    session: Session = Depends(get_session)
):
    """Crée un nouvel hôtel (réservé aux administrateurs)"""
    existing_hotel = session.exec(select(Hotel).where(Hotel.hotel_id == hotel_id)).first()
    if existing_hotel:
        raise HTTPException(status_code=409, detail=f"L'ID d'hôtel '{hotel_id}' existe déjà.")
    
    hotel = Hotel(hotel_id=hotel_id, name=name)
    session.add(hotel)
    session.commit()
    session.refresh(hotel)
    
    return {"status": "ok", "hotel_id": hotel.hotel_id, "name": hotel.name}

@router.get("/", response_model=List[dict])
async def get_all_hotels(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Récupère la liste de tous les hôtels (limitée aux hôtels accessibles pour les utilisateurs non-admin)"""
    if current_user.role == "admin":
        hotels = session.exec(select(Hotel)).all()
    else:
        # Pour les utilisateurs non-admin, récupérer uniquement les hôtels auxquels ils ont accès
        from models import UserHotelPermission
        permissions = session.exec(
            select(UserHotelPermission)
            .where(UserHotelPermission.user_id == current_user.id)
            .where(UserHotelPermission.access_expires_at > datetime.now())
        ).all()
        
        hotel_ids = [perm.hotel_id for perm in permissions]
        hotels = session.exec(select(Hotel).where(Hotel.hotel_id.in_(hotel_ids))).all()
    
    return [{"hotel_id": hotel.hotel_id, "name": hotel.name} for hotel in hotels]

@router.delete("/{hotel_id}")
async def delete_hotel(
    hotel_id: str,
    current_user: User = Depends(get_admin_user),
    session: Session = Depends(get_session)
):
    """Supprime un hôtel (réservé aux administrateurs)"""
    hotel = session.exec(select(Hotel).where(Hotel.hotel_id == hotel_id)).first()
    if not hotel:
        raise HTTPException(status_code=404, detail="Hôtel non trouvé.")
    
    session.delete(hotel)
    session.commit()
    
    return {"status": "ok", "message": f"Hôtel '{hotel_id}' supprimé."}
