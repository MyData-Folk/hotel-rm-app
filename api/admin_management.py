from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime
import pandas as pd
import json
import io
from supabase import create_client
from pydantic import BaseModel

from models import (
    User, Hotel, UserHotelPermission, AdminUserManagement, 
    AdminTariffPlans, AdminConfiguration, AdminAuditLog, UserRole
)
from auth import get_current_user, verify_token
from database import get_supabase_client

router = APIRouter()

# Configuration Supabase
supabase = get_supabase_client()

# Modèles Pydantic pour les requêtes
class HotelCreateRequest(BaseModel):
    hotel_id: str
    hotel_name: str
    admin_email: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

class TariffUploadRequest(BaseModel):
    hotel_id: str
    plan_name: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None

class ConfigUploadRequest(BaseModel):
    hotel_id: str
    config_name: str
    version: Optional[str] = "1.0"

class AuditLogRequest(BaseModel):
    hotel_id: Optional[str] = None
    action: Optional[str] = None
    limit: int = 100

# Fonctions utilitaires
async def log_admin_action(hotel_id: str, action: str, table_name: str, 
                         record_id: Optional[str] = None, old_values: Optional[Dict] = None, 
                         new_values: Optional[Dict] = None, performed_by: str = None):
    """Journalise une action dans l'audit log"""
    try:
        audit_data = {
            "hotel_id": hotel_id,
            "action": action,
            "table_name": table_name,
            "record_id": record_id,
            "old_values": old_values,
            "new_values": new_values,
            "performed_by": performed_by,
            "performed_at": datetime.now().isoformat()
        }
        
        await supabase.table("admin_audit_log").insert(audit_data).execute()
        return True
    except Exception as e:
        print(f"Erreur lors de la journalisation: {e}")
        return False

async def increment_version(current_version: str) -> str:
    """Incrémente la version d'une configuration"""
    if not current_version or current_version == "":
        return "1.0"
    
    try:
        if "." in current_version:
            major, minor = current_version.split(".")
            return f"{major}.{int(minor) + 1}"
        else:
            return str(int(current_version) + 1)
    except:
        return "1.0"

async def validate_admin_access(current_user: Dict, required_permission: str = "admin") -> bool:
    """Valide que l'utilisateur a les permissions admin"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Utilisateur non authentifié")
    
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Accès admin requis")
    
    return True

async def validate_hotel_ownership(current_user: Dict, hotel_id: str) -> bool:
    """Valide que l'admin gère bien cet hôtel"""
    try:
        result = await supabase.table("admin_user_management").select("*").eq(
            "admin_email", current_user["email"]
        ).eq("hotel_id", hotel_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=403, detail="Hôtel non géré par cet admin")
        
        return True
    except Exception as e:
        raise HTTPException(status_code=403, detail=f"Erreur validation hôtel: {e}")

# === ENDPOINTS DE GESTION DES HÔTELS ===

@router.post("/hotels/create")
async def create_hotel(
    request: HotelCreateRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Crée un nouvel hôtel et toutes ses tables associées"""
    
    await validate_admin_access(current_user)
    
    try:
        # Vérifier que l'hôtel n'existe pas déjà
        existing_hotel = await supabase.table("admin_user_management").select("*").eq(
            "hotel_id", request.hotel_id
        ).execute()
        
        if existing_hotel.data:
            raise HTTPException(status_code=400, detail="Cet hôtel existe déjà")
        
        # Créer l'entrée principale
        hotel_data = {
            "hotel_id": request.hotel_id,
            "hotel_name": request.hotel_name,
            "admin_email": request.admin_email,
            "contact_email": request.contact_email,
            "contact_phone": request.contact_phone,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # Insérer dans la table principale
        result = await supabase.table("admin_user_management").insert(hotel_data).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Erreur lors de la création de l'hôtel")
        
        # Créer les entrées vides dans les autres tables
        tariff_data = {
            "hotel_id": request.hotel_id,
            "plan_name": "Initial",
            "plan_data": {},
            "status": "active",
            "upload_date": datetime.now().isoformat()
        }
        
        config_data = {
            "hotel_id": request.hotel_id,
            "config_name": "Initial",
            "config_data": {},
            "version": "1.0",
            "status": "active",
            "upload_date": datetime.now().isoformat()
        }
        
        await supabase.table("admin_tariff_plans").insert(tariff_data).execute()
        await supabase.table("admin_configuration").insert(config_data).execute()
        
        # Journaliser l'action
        await log_admin_action(
            hotel_id=request.hotel_id,
            action="create_hotel",
            table_name="admin_user_management",
            new_values=hotel_data,
            performed_by=current_user["email"]
        )
        
        return {
            "message": "Hôtel créé avec succès",
            "hotel_id": request.hotel_id,
            "hotel_name": request.hotel_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création: {str(e)}")

@router.get("/hotels")
async def get_all_hotels(
    current_user: Dict = Depends(get_current_user),
    status: Optional[str] = "active"
):
    """Récupère tous les hôtels (admin seulement)"""
    
    await validate_admin_access(current_user)
    
    try:
        query = supabase.table("admin_user_management").select("*")
        
        if status:
            query = query.eq("status", status)
        
        result = await query.execute()
        
        if not result.data:
            return {"hotels": []}
        
        # Récupérer les statistiques pour chaque hôtel
        hotels_with_stats = []
        for hotel in result.data:
            # Compter les utilisateurs
            users_count = await supabase.table("user_hotel_permissions").select(
                "id", count="exact"
            ).eq("hotel_id", hotel["hotel_id"]).execute()
            
            # Dernière mise à jour
            last_update = await supabase.table("admin_tariff_plans").select(
                "upload_date"
            ).eq("hotel_id", hotel["hotel_id"]).eq("status", "active").order(
                "upload_date", desc=True
            ).limit(1).execute()
            
            hotel["users_count"] = len(users_count.data) if users_count.data else 0
            hotel["last_update"] = last_update.data[0]["upload_date"] if last_update.data else None
            
            hotels_with_stats.append(hotel)
        
        return {"hotels": hotels_with_stats}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

@router.get("/hotels/{hotel_id}")
async def get_hotel_details(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère les détails d'un hôtel spécifique"""
    
    await validate_admin_access(current_user)
    await validate_hotel_ownership(current_user, hotel_id)
    
    try:
        # Récupérer les informations de l'hôtel
        hotel_info = await supabase.table("admin_user_management").select("*").eq(
            "hotel_id", hotel_id
        ).execute()
        
        if not hotel_info.data:
            raise HTTPException(status_code=404, detail="Hôtel non trouvé")
        
        hotel = hotel_info.data[0]
        
        # Récupérer les plans tarifaires
        tariff_plans = await supabase.table("admin_tariff_plans").select("*").eq(
            "hotel_id", hotel_id
        ).order("upload_date", desc=True).execute()
        
        # Récupérer les configurations
        configurations = await supabase.table("admin_configuration").select("*").eq(
            "hotel_id", hotel_id
        ).order("upload_date", desc=True).execute()
        
        # Récupérer les utilisateurs
        users = await supabase.table("user_hotel_permissions").select("*").eq(
            "hotel_id", hotel_id
        ).execute()
        
        return {
            "hotel": hotel,
            "tariff_plans": tariff_plans.data,
            "configurations": configurations.data,
            "users": users.data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

@router.put("/hotels/{hotel_id}")
async def update_hotel(
    hotel_id: str,
    hotel_data: Dict[str, Any],
    current_user: Dict = Depends(get_current_user)
):
    """Met à jour les informations d'un hôtel"""
    
    await validate_admin_access(current_user)
    await validate_hotel_ownership(current_user, hotel_id)
    
    try:
        # Ajouter la date de mise à jour
        hotel_data["updated_at"] = datetime.now().isoformat()
        
        # Récupérer les anciennes valeurs pour l'audit
        old_hotel = await supabase.table("admin_user_management").select("*").eq(
            "hotel_id", hotel_id
        ).execute()
        
        if not old_hotel.data:
            raise HTTPException(status_code=404, detail="Hôtel non trouvé")
        
        old_values = old_hotel.data[0]
        
        # Mettre à jour l'hôtel
        result = await supabase.table("admin_user_management").update(
            hotel_data
        ).eq("hotel_id", hotel_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour")
        
        # Journaliser l'action
        await log_admin_action(
            hotel_id=hotel_id,
            action="update_hotel",
            table_name="admin_user_management",
            old_values=old_values,
            new_values=hotel_data,
            performed_by=current_user["email"]
        )
        
        return {
            "message": "Hôtel mis à jour avec succès",
            "hotel_id": hotel_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour: {str(e)}")

@router.delete("/hotels/{hotel_id}")
async def delete_hotel(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Supprime un hôtel (soft delete)"""
    
    await validate_admin_access(current_user)
    await validate_hotel_ownership(current_user, hotel_id)
    
    try:
        # Récupérer les anciennes valeurs pour l'audit
        old_hotel = await supabase.table("admin_user_management").select("*").eq(
            "hotel_id", hotel_id
        ).execute()
        
        if not old_hotel.data:
            raise HTTPException(status_code=404, detail="Hôtel non trouvé")
        
        old_values = old_hotel.data[0]
        
        # Mettre à jour le statut à "deleted"
        result = await supabase.table("admin_user_management").update(
            {"status": "deleted", "updated_at": datetime.now().isoformat()}
        ).eq("hotel_id", hotel_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Erreur lors de la suppression")
        
        # Journaliser l'action
        await log_admin_action(
            hotel_id=hotel_id,
            action="delete_hotel",
            table_name="admin_user_management",
            old_values=old_values,
            performed_by=current_user["email"]
        )
        
        return {
            "message": "Hôtel supprimé avec succès",
            "hotel_id": hotel_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")

# === ENDPOINTS DE GESTION DES PLANS TARIFAIRES ===

@router.post("/hotels/{hotel_id}/tariff/upload")
async def upload_tariff_plan(
    hotel_id: str,
    file: UploadFile = File(...),
    request: TariffUploadRequest = Depends(),
    current_user: Dict = Depends(get_current_user)
):
    """Upload un plan tarifaire pour un hôtel"""
    
    await validate_admin_access(current_user)
    await validate_hotel_ownership(current_user, hotel_id)
    
    try:
        # Vérifier le type de fichier
        if not file.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
            raise HTTPException(status_code=400, detail="Format de fichier non supporté")
        
        # Lire le fichier
        content = await file.read()
        
        # Parser le fichier
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(io.StringIO(content.decode('utf-8')))
        else:
            df = pd.read_excel(io.BytesIO(content))
        
        # Convertir en JSON
        tariff_data = df.to_dict('records')
        
        # Vérifier si un plan existe déjà
        existing_plan = await supabase.table("admin_tariff_plans").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").execute()
        
        tariff_info = {
            "hotel_id": hotel_id,
            "plan_name": request.plan_name,
            "plan_data": tariff_data,
            "file_name": file.filename,
            "file_size": len(content),
            "upload_date": datetime.now().isoformat(),
            "uploaded_by": current_user["email"],
            "valid_from": request.valid_from,
            "valid_to": request.valid_to,
            "status": "active"
        }
        
        if existing_plan.data:
            # Mettre à jour le plan existant
            await supabase.table("admin_tariff_plans").update(
                tariff_info
            ).eq("hotel_id", hotel_id).eq("status", "active").execute()
            
            action = "update_tariff"
        else:
            # Créer un nouveau plan
            await supabase.table("admin_tariff_plans").insert(tariff_info).execute()
            
            action = "create_tariff"
        
        # Journaliser l'action
        await log_admin_action(
            hotel_id=hotel_id,
            action=action,
            table_name="admin_tariff_plans",
            new_values=tariff_info,
            performed_by=current_user["email"]
        )
        
        return {
            "message": "Plan tarifaire uploadé avec succès",
            "hotel_id": hotel_id,
            "plan_name": request.plan_name,
            "rows_count": len(tariff_data)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'upload: {str(e)}")

@router.get("/hotels/{hotel_id}/tariff")
async def get_tariff_plan(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère le plan tarifaire actif d'un hôtel"""
    
    await validate_admin_access(current_user)
    await validate_hotel_ownership(current_user, hotel_id)
    
    try:
        tariff_data = await supabase.table("admin_tariff_plans").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").order("upload_date", desc=True).limit(1).execute()
        
        if not tariff_data.data:
            raise HTTPException(status_code=404, detail="Aucun plan tarifaire trouvé")
        
        return {
            "hotel_id": hotel_id,
            "tariff_plan": tariff_data.data[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

@router.get("/hotels/{hotel_id}/tariff/history")
async def get_tariff_history(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère l'historique des plans tarifaires"""
    
    await validate_admin_access(current_user)
    await validate_hotel_ownership(current_user, hotel_id)
    
    try:
        tariff_history = await supabase.table("admin_tariff_plans").select("*").eq(
            "hotel_id", hotel_id
        ).order("upload_date", desc=True).execute()
        
        return {
            "hotel_id": hotel_id,
            "tariff_history": tariff_history.data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

# === ENDPOINTS DE GESTION DE LA CONFIGURATION ===

@router.post("/hotels/{hotel_id}/config/upload")
async def upload_configuration(
    hotel_id: str,
    file: UploadFile = File(...),
    request: ConfigUploadRequest = Depends(),
    current_user: Dict = Depends(get_current_user)
):
    """Upload une configuration JSON pour un hôtel"""
    
    await validate_admin_access(current_user)
    await validate_hotel_ownership(current_user, hotel_id)
    
    try:
        # Vérifier le type de fichier
        if not file.filename.lower().endswith('.json'):
            raise HTTPException(status_code=400, detail="Format de fichier non supporté")
        
        # Lire le fichier
        content = await file.read()
        
        # Parser le JSON
        config_data = json.loads(content.decode('utf-8'))
        
        # Récupérer la version actuelle
        current_config = await supabase.table("admin_configuration").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").execute()
        
        config_info = {
            "hotel_id": hotel_id,
            "config_name": request.config_name,
            "config_data": config_data,
            "file_name": file.filename,
            "file_size": len(content),
            "upload_date": datetime.now().isoformat(),
            "uploaded_by": current_user["email"],
            "version": request.version,
            "status": "active"
        }
        
        if current_config.data:
            # Mettre à jour la configuration existante
            await supabase.table("admin_configuration").update(
                config_info
            ).eq("hotel_id", hotel_id).eq("status", "active").execute()
            
            action = "update_config"
        else:
            # Créer une nouvelle configuration
            await supabase.table("admin_configuration").insert(config_info).execute()
            
            action = "create_config"
        
        # Journaliser l'action
        await log_admin_action(
            hotel_id=hotel_id,
            action=action,
            table_name="admin_configuration",
            new_values=config_info,
            performed_by=current_user["email"]
        )
        
        return {
            "message": "Configuration uploadée avec succès",
            "hotel_id": hotel_id,
            "config_name": request.config_name,
            "version": request.version
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'upload: {str(e)}")

@router.get("/hotels/{hotel_id}/config")
async def get_configuration(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère la configuration active d'un hôtel"""
    
    await validate_admin_access(current_user)
    await validate_hotel_ownership(current_user, hotel_id)
    
    try:
        config_data = await supabase.table("admin_configuration").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").order("upload_date", desc=True).limit(1).execute()
        
        if not config_data.data:
            raise HTTPException(status_code=404, detail="Aucune configuration trouvée")
        
        return {
            "hotel_id": hotel_id,
            "configuration": config_data.data[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

@router.get("/hotels/{hotel_id}/config/history")
async def get_config_history(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère l'historique des configurations"""
    
    await validate_admin_access(current_user)
    await validate_hotel_ownership(current_user, hotel_id)
    
    try:
        config_history = await supabase.table("admin_configuration").select("*").eq(
            "hotel_id", hotel_id
        ).order("upload_date", desc=True).execute()
        
        return {
            "hotel_id": hotel_id,
            "config_history": config_history.data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

# === ENDPOINTS D'AUDIT LOG ===

@router.get("/audit-log")
async def get_audit_log(
    request: AuditLogRequest = Depends(),
    current_user: Dict = Depends(get_current_user)
):
    """Récupère l'historique des modifications"""
    
    await validate_admin_access(current_user)
    
    try:
        query = supabase.table("admin_audit_log").select("*")
        
        if request.hotel_id:
            query = query.eq("hotel_id", request.hotel_id)
        
        if request.action:
            query = query.eq("action", request.action)
        
        query = query.order("performed_at", desc=True).limit(request.limit)
        
        audit_log = await query.execute()
        
        return {
            "audit_log": audit_log.data,
            "total": len(audit_log.data) if audit_log.data else 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

@router.get("/audit-log/export")
async def export_audit_log(
    format: str = "json",
    current_user: Dict = Depends(get_current_user)
):
    """Exporte l'historique des modifications"""
    
    await validate_admin_access(current_user)
    
    try:
        audit_log = await supabase.table("admin_audit_log").select("*").order(
            "performed_at", desc=True
        ).execute()
        
        if not audit_log.data:
            return {"message": "Aucune donnée à exporter"}
        
        if format.lower() == "csv":
            # Convertir en CSV
            df = pd.DataFrame(audit_log.data)
            csv_data = df.to_csv(index=False)
            
            return JSONResponse(
                content={"csv_data": csv_data},
                headers={"Content-Disposition": "attachment; filename=audit_log.csv"}
            )
        else:
            # Retourner JSON
            return {"audit_log": audit_log.data}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'export: {str(e)}")

# === ENDPOINTS DE STATISTIQUES ===

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    current_user: Dict = Depends(get_current_user)
):
    """Récupère les statistiques du dashboard admin"""
    
    await validate_admin_access(current_user)
    
    try:
        # Statistiques générales
        hotels_count = await supabase.table("admin_user_management").select(
            "id", count="exact"
        ).eq("status", "active").execute()
        
        users_count = await supabase.table("user_hotel_permissions").select(
            "id", count="exact"
        ).execute()
        
        tariff_plans_count = await supabase.table("admin_tariff_plans").select(
            "id", count="exact"
        ).execute()
        
        config_count = await supabase.table("admin_configuration").select(
            "id", count="exact"
        ).execute()
        
        # Activité récente
        recent_activity = await supabase.table("admin_audit_log").select("*").order(
            "performed_at", desc=True
        ).limit(10).execute()
        
        return {
            "stats": {
                "hotels": len(hotels_count.data) if hotels_count.data else 0,
                "users": len(users_count.data) if users_count.data else 0,
                "tariff_plans": len(tariff_plans_count.data) if tariff_plans_count.data else 0,
                "configurations": len(config_count.data) if config_count.data else 0
            },
            "recent_activity": recent_activity.data if recent_activity.data else []
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

# === ENDPOINTS DE SYSTÈME ===

@router.get("/system/health")
async def get_system_health():
    """Vérifie la santé du système"""
    
    try:
        # Vérifier la connexion à Supabase
        health_check = await supabase.table("admin_user_management").select("id").limit(1).execute()
        
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@router.post("/system/reset/{hotel_id}")
async def reset_hotel_data(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Réinitialise les données d'un hôtel"""
    
    await validate_admin_access(current_user)
    await validate_hotel_ownership(current_user, hotel_id)
    
    try:
        # Récupérer les anciennes valeurs pour l'audit
        old_tariff = await supabase.table("admin_tariff_plans").select("*").eq(
            "hotel_id", hotel_id
        ).execute()
        
        old_config = await supabase.table("admin_configuration").select("*").eq(
            "hotel_id", hotel_id
        ).execute()
        
        # Supprimer les données existantes
        await supabase.table("admin_tariff_plans").delete().eq("hotel_id", hotel_id).execute()
        await supabase.table("admin_configuration").delete().eq("hotel_id", hotel_id).execute()
        
        # Créer des données vides
        tariff_data = {
            "hotel_id": hotel_id,
            "plan_name": "Initial",
            "plan_data": {},
            "status": "active",
            "upload_date": datetime.now().isoformat()
        }
        
        config_data = {
            "hotel_id": hotel_id,
            "config_name": "Initial",
            "config_data": {},
            "version": "1.0",
            "status": "active",
            "upload_date": datetime.now().isoformat()
        }
        
        await supabase.table("admin_tariff_plans").insert(tariff_data).execute()
        await supabase.table("admin_configuration").insert(config_data).execute()
        
        # Journaliser l'action
        await log_admin_action(
            hotel_id=hotel_id,
            action="reset_hotel_data",
            table_name="all",
            old_values={"tariff": old_tariff.data, "config": old_config.data},
            new_values={"tariff": tariff_data, "config": config_data},
            performed_by=current_user["email"]
        )
        
        return {
            "message": "Données de l'hôtel réinitialisées avec succès",
            "hotel_id": hotel_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la réinitialisation: {str(e)}")
