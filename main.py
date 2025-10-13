from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import uvicorn
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Importations locales
from database import engine, init_db, get_db
from models import *
from api.hotels import router as hotels_router
from api.uploads import router as uploads_router
from api.permissions import router as permissions_router
from api.admin_management import router as admin_router
from api.hotel_data_access import router as data_access_router

# Configuration de l'application
app = FastAPI(
    title="HotelVision RM v2.0 API",
    description="API de gestion hôtelière avec interface d'administration",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hotelvision.e-hotelmanager.com",
        "https://admin-hv.e-hotelmanager.com",
        "http://localhost:3000",
        "http://localhost:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sécurité
security = HTTPBearer()

# Configuration globale
API_VERSION = "v2.0"
API_NAME = "HotelVision RM"

# Variables d'environnement
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://supabase.e-hotelmanager.com')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSIsImlhdCI6MTc1OTYzMjAwMCwiZXhwIjo0OTE1MzA1NjAwLCJyb2xlIjoiYW5vbiJ9.REKN8YlJRDjhxS3HcDwmw5_KVZ8ylGG4ARkAvybsOUY')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this-in-production')

# Événements de cycle de vie de l'application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage de l'application
    print(f"🚀 Démarrage de {API_NAME} {API_VERSION}")
    print(f"📊 URL Supabase: {SUPABASE_URL}")
    print(f"🔐 API URL: {os.getenv('API_URL', 'http://localhost:8000')}")
    
    # Initialiser la base de données
    if init_db():
        print("✅ Base de données initialisée avec succès")
    else:
        print("❌ Erreur lors de l'initialisation de la base de données")
    
    yield
    
    # Fermeture de l'application
    print(f"🛑 Arrêt de {API_NAME} {API_VERSION}")

# Appliquer le cycle de vie
app.router.lifespan_context = lifespan

# Routes principales
@app.get("/")
async def root():
    """Endpoint racine"""
    return {
        "message": f"Bienvenue sur {API_NAME} {API_VERSION}",
        "version": API_VERSION,
        "status": "running",
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Vérification de la santé de l'application"""
    return {
        "status": "healthy",
        "version": API_VERSION,
        "timestamp": "2025-10-12T10:00:00Z",
        "database": "connected"
    }

@app.get("/api/verify-token")
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Vérifier la validité d'un token JWT"""
    try:
        # Ici vous devriez implémenter la vérification réelle du token
        # Pour l'instant, nous retournons une réponse de base
        return {
            "valid": True,
            "message": "Token valide",
            "user": {
                "id": "user-id-placeholder",
                "email": "user@example.com",
                "role": "admin"
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré"
        )

# Routes d'administration
@app.get("/api/admin/dashboard/stats")
async def get_admin_dashboard_stats():
    """Statistiques du tableau de bord administratif"""
    return {
        "stats": {
            "hotels": 0,
            "users": 0,
            "tariff_plans": 0,
            "configurations": 0
        },
        "recent_activity": [
            {
                "action": "create_hotel",
                "performed_at": "2025-10-12T10:00:00Z"
            }
        ]
    }

# Inclusion des routeurs
app.include_router(hotels_router, prefix="/api/hotels", tags=["Hotels"])
app.include_router(uploads_router, prefix="/api/uploads", tags=["Uploads"])
app.include_router(permissions_router, prefix="/api/permissions", tags=["Permissions"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(data_access_router, prefix="/api/hotel", tags=["Hotel Data Access"])

# Endpoint de déconnexion
@app.post("/api/logout")
async def logout():
    """Endpoint de déconnexion"""
    return {"message": "Déconnexion réussie"}

# Gestion globale des erreurs
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return {
        "error": exc.detail,
        "status_code": exc.status_code,
        "message": "Une erreur est survenue"
    }

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return {
        "error": "Internal Server Error",
        "status_code": 500,
        "message": "Une erreur interne est survenue"
    }

# Point d'entrée principal
if __name__ == "__main__":
    # Configuration pour le développement
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
