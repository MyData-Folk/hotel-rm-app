from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlmodel import Session, select
from datetime import datetime

from database import get_session
from models import User, UserRole

# Configuration
SUPABASE_JWT_SECRET = "your-jwt-secret"
ALGORITHM = "HS256"

security = HTTPBearer()

async def verify_token(token: str) -> User:
    """Vérifie la validité du token JWT et retourne l'utilisateur correspondant"""
    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        role: str = payload.get("app_metadata", {}).get("role", "user")
        
        if user_id is None or email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Créer un objet utilisateur à partir des données du token
        user = User(
            id=user_id,
            email=email,
            role=UserRole(role) if role in [r.value for r in UserRole] else UserRole.USER
        )
        
        return user
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session)
) -> User:
    """Dépendance pour obtenir l'utilisateur actuel à partir du token JWT"""
    token = credentials.credentials
    user = await verify_token(token)
    
    # Vérifier si l'utilisateur existe dans notre base de données
    db_user = session.exec(select(User).where(User.id == user.id)).first()
    if not db_user:
        # Créer l'utilisateur dans notre base de données s'il n'existe pas
        db_user = User(
            id=user.id,
            email=user.email,
            role=user.role
        )
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    
    return db_user

async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Dépendance pour vérifier si l'utilisateur est un administrateur"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes"
        )
    return current_user

def check_hotel_permission(
    hotel_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Vérifie si l'utilisateur a accès à l'hôtel spécifié"""
    if current_user.role == UserRole.ADMIN:
        return True  # Les administrateurs ont accès à tous les hôtels
    
    # Vérifier si l'utilisateur a une permission active pour cet hôtel
    permission = session.exec(
        select(UserHotelPermission)
        .where(UserHotelPermission.user_id == current_user.id)
        .where(UserHotelPermission.hotel_id == hotel_id)
        .where(UserHotelPermission.access_expires_at > datetime.now())
    ).first()
    
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'avez pas les droits suffisants pour accéder à cet hôtel"
        )
    
    return True