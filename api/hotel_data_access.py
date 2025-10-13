from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
from datetime import datetime
import pandas as pd

from models import User, Hotel, UserHotelPermission, AdminTariffPlans, AdminConfiguration
from auth import get_current_user
from database import get_supabase_client

router = APIRouter()

# Configuration Supabase
supabase = get_supabase_client()

# Fonctions utilitaires
async def validate_hotel_access(user_id: str, hotel_id: str) -> bool:
    """Valide que l'utilisateur a accès à l'hôtel"""
    try:
        result = await supabase.table("user_hotel_permissions").select("*").eq(
            "user_id", user_id
        ).eq("hotel_id", hotel_id).execute()
        
        if not result.data:
            return False
        
        # Vérifier si l'accès n'est pas expiré
        permission = result.data[0]
        access_expires_at = datetime.fromisoformat(permission["access_expires_at"])
        
        if datetime.now() > access_expires_at:
            return False
        
        return True
    except Exception as e:
        print(f"Erreur validation accès: {e}")
        return False

# === ENDPOINTS DE LECTURE DES DONNÉES POUR LES HÔTELS ===

@router.get("/tariff-data")
async def get_tariff_data(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère les données tarifaires pour un hôtel (lecture seule)"""
    
    try:
        # Vérifier que l'utilisateur a accès à cet hôtel
        if not await validate_hotel_access(current_user["id"], hotel_id):
            raise HTTPException(status_code=403, detail="Accès refusé à cet hôtel")
        
        # Récupérer le plan tarifaire actif
        tariff_data = await supabase.table("admin_tariff_plans").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").order("upload_date", desc=True).limit(1).execute()
        
        if not tariff_data.data:
            raise HTTPException(status_code=404, detail="Aucun plan tarifaire trouvé")
        
        tariff_plan = tariff_data.data[0]
        
        # Filtrer et valider les données
        if not tariff_plan.get("plan_data"):
            tariff_plan["plan_data"] = []
        
        # Valider la structure des données
        validated_data = []
        for record in tariff_plan["plan_data"]:
            if isinstance(record, dict) and "room_type" in record and "rate_plan" in record:
                validated_data.append(record)
        
        return {
            "hotel_id": hotel_id,
            "tariff_plan": {
                "id": tariff_plan["id"],
                "plan_name": tariff_plan["plan_name"],
                "file_name": tariff_plan["file_name"],
                "upload_date": tariff_plan["upload_date"],
                "valid_from": tariff_plan["valid_from"],
                "valid_to": tariff_plan["valid_to"],
                "status": tariff_plan["status"]
            },
            "data": validated_data,
            "data_count": len(validated_data),
            "last_updated": tariff_plan["upload_date"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

@router.get("/configuration")
async def get_configuration(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère la configuration pour un hôtel (lecture seule)"""
    
    try:
        # Vérifier que l'utilisateur a accès à cet hôtel
        if not await validate_hotel_access(current_user["id"], hotel_id):
            raise HTTPException(status_code=403, detail="Accès refusé à cet hôtel")
        
        # Récupérer la configuration active
        config_data = await supabase.table("admin_configuration").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").order("upload_date", desc=True).limit(1).execute()
        
        if not config_data.data:
            raise HTTPException(status_code=404, detail="Aucune configuration trouvée")
        
        config = config_data.data[0]
        
        # Valider la structure des données
        if not config.get("config_data"):
            config["config_data"] = {}
        
        # Filtrer les champs sensibles si nécessaire
        safe_config = {
            "mapping": config["config_data"].get("mapping", {}),
            "settings": config["config_data"].get("settings", {}),
            "custom_fields": config["config_data"].get("custom_fields", {})
        }
        
        return {
            "hotel_id": hotel_id,
            "configuration": {
                "id": config["id"],
                "config_name": config["config_name"],
                "file_name": config["file_name"],
                "version": config["version"],
                "upload_date": config["upload_date"],
                "status": config["status"]
            },
            "data": safe_config,
            "last_updated": config["upload_date"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

@router.get("/hotel-info")
async def get_hotel_info(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère les informations de base de l'hôtel"""
    
    try:
        # Vérifier que l'utilisateur a accès à cet hôtel
        if not await validate_hotel_access(current_user["id"], hotel_id):
            raise HTTPException(status_code=403, detail="Accès refusé à cet hôtel")
        
        # Récupérer les informations de l'hôtel
        hotel_info = await supabase.table("admin_user_management").select("*").eq(
            "hotel_id", hotel_id
        ).execute()
        
        if not hotel_info.data:
            raise HTTPException(status_code=404, detail="Hôtel non trouvé")
        
        hotel = hotel_info.data[0]
        
        # Ne retourner que les informations publiques
        public_info = {
            "hotel_id": hotel["hotel_id"],
            "hotel_name": hotel["hotel_name"],
            "contact_email": hotel.get("contact_email"),
            "contact_phone": hotel.get("contact_phone"),
            "status": hotel["status"],
            "created_at": hotel["created_at"]
        }
        
        return {
            "hotel_id": hotel_id,
            "hotel_info": public_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

# === ENDPOINTS DE STATISTIQUES POUR LES HÔTELS ===

@router.get("/stats")
async def get_hotel_stats(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère les statistiques pour un hôtel spécifique"""
    
    try:
        # Vérifier que l'utilisateur a accès à cet hôtel
        if not await validate_hotel_access(current_user["id"], hotel_id):
            raise HTTPException(status_code=403, detail="Accès refusé à cet hôtel")
        
        # Récupérer les statistiques des tarifs
        tariff_stats = await supabase.table("admin_tariff_plans").select("*").eq(
            "hotel_id", hotel_id
        ).execute()
        
        # Récupérer les statistiques des configurations
        config_stats = await supabase.table("admin_configuration").select("*").eq(
            "hotel_id", hotel_id
        ).execute()
        
        # Compter les types de tarifs
        tariff_data = tariff_stats.data if tariff_stats.data else []
        active_tariffs = [t for t in tariff_data if t.get("status") == "active"]
        
        # Compter les versions de configuration
        config_data = config_stats.data if config_stats.data else []
        active_configs = [c for c in config_data if c.get("status") == "active"]
        
        # Analyser les données tarifaires
        total_rooms = 0
        unique_rate_plans = set()
        
        for tariff in active_tariffs:
            plan_data = tariff.get("plan_data", [])
            for record in plan_data:
                if isinstance(record, dict):
                    if "room_type" in record:
                        total_rooms += 1
                    if "rate_plan" in record:
                        unique_rate_plans.add(record["rate_plan"])
        
        return {
            "hotel_id": hotel_id,
            "stats": {
                "total_tariff_plans": len(tariff_data),
                "active_tariff_plans": len(active_tariffs),
                "total_configurations": len(config_data),
                "active_configurations": len(active_configs),
                "total_rooms": total_rooms,
                "unique_rate_plans": len(unique_rate_plans)
            },
            "last_updated": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

@router.get("/data-summary")
async def get_data_summary(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère un résumé des données de l'hôtel"""
    
    try:
        # Vérifier que l'utilisateur a accès à cet hôtel
        if not await validate_hotel_access(current_user["id"], hotel_id):
            raise HTTPException(status_code=403, detail="Accès refusé à cet hôtel")
        
        # Récupérer le plan tarifaire actif
        tariff_data = await supabase.table("admin_tariff_plans").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").order("upload_date", desc=True).limit(1).execute()
        
        # Récupérer la configuration active
        config_data = await supabase.table("admin_configuration").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").order("upload_date", desc=True).limit(1).execute()
        
        # Analyser les données tarifaires
        tariff_summary = {}
        if tariff_data.data:
            tariff_plan = tariff_data.data[0]
            plan_data = tariff_plan.get("plan_data", [])
            
            # Grouper par type de chambre
            rooms_by_type = {}
            rates_by_plan = {}
            
            for record in plan_data:
                if isinstance(record, dict):
                    room_type = record.get("room_type", "Unknown")
                    rate_plan = record.get("rate_plan", "Unknown")
                    price = record.get("price", 0)
                    
                    if room_type not in rooms_by_type:
                        rooms_by_type[room_type] = []
                    rooms_by_type[room_type].append(price)
                    
                    if rate_plan not in rates_by_plan:
                        rates_by_plan[rate_plan] = []
                    rates_by_plan[rate_plan].append(price)
            
            # Calculer les statistiques
            tariff_summary = {
                "total_records": len(plan_data),
                "room_types": len(rooms_by_type),
                "rate_plans": len(rates_by_plan),
                "rooms": {
                    type: {
                        "count": len(prices),
                        "avg_price": sum(prices) / len(prices) if prices else 0,
                        "min_price": min(prices) if prices else 0,
                        "max_price": max(prices) if prices else 0
                    }
                    for type, prices in rooms_by_type.items()
                },
                "rate_plans_summary": {
                    plan: {
                        "count": len(prices),
                        "avg_price": sum(prices) / len(prices) if prices else 0
                    }
                    for plan, prices in rates_by_plan.items()
                }
            }
        
        # Résumer la configuration
        config_summary = {}
        if config_data.data:
            config = config_data.data[0]
            config_data_dict = config.get("config_data", {})
            
            config_summary = {
                "config_name": config.get("config_name"),
                "version": config.get("version"),
                "mapping_fields": len(config_data_dict.get("mapping", {})),
                "settings_count": len(config_data_dict.get("settings", {})),
                "custom_fields_count": len(config_data_dict.get("custom_fields", {}))
            }
        
        return {
            "hotel_id": hotel_id,
            "tariff_summary": tariff_summary,
            "config_summary": config_summary,
            "last_updated": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

# === ENDPOINTS D'EXPORT POUR LES HÔTELS ===

@router.get("/export/tariff")
async def export_tariff_data(
    hotel_id: str,
    format: str = "json",
    current_user: Dict = Depends(get_current_user)
):
    """Exporte les données tarifaires"""
    
    try:
        # Vérifier que l'utilisateur a accès à cet hôtel
        if not await validate_hotel_access(current_user["id"], hotel_id):
            raise HTTPException(status_code=403, detail="Accès refusé à cet hôtel")
        
        # Récupérer le plan tarifaire actif
        tariff_data = await supabase.table("admin_tariff_plans").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").order("upload_date", desc=True).limit(1).execute()
        
        if not tariff_data.data:
            raise HTTPException(status_code=404, detail="Aucun plan tarifaire trouvé")
        
        tariff_plan = tariff_data.data[0]
        plan_data = tariff_plan.get("plan_data", [])
        
        if format.lower() == "csv":
            # Convertir en CSV
            df = pd.DataFrame(plan_data)
            csv_data = df.to_csv(index=False)
            
            return JSONResponse(
                content={"csv_data": csv_data},
                headers={"Content-Disposition": f"attachment; filename=tariff_{hotel_id}.csv"}
            )
        elif format.lower() == "excel":
            # Convertir en Excel
            df = pd.DataFrame(plan_data)
            excel_data = df.to_excel(index=False)
            
            return JSONResponse(
                content={"excel_data": excel_data},
                headers={"Content-Disposition": f"attachment; filename=tariff_{hotel_id}.xlsx"}
            )
        else:
            # Retourner JSON
            return {
                "hotel_id": hotel_id,
                "tariff_plan": tariff_plan,
                "data": plan_data
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'export: {str(e)}")

@router.get("/export/config")
async def export_config_data(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Exporte la configuration"""
    
    try:
        # Vérifier que l'utilisateur a accès à cet hôtel
        if not await validate_hotel_access(current_user["id"], hotel_id):
            raise HTTPException(status_code=403, detail="Accès refusé à cet hôtel")
        
        # Récupérer la configuration active
        config_data = await supabase.table("admin_configuration").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").order("upload_date", desc=True).limit(1).execute()
        
        if not config_data.data:
            raise HTTPException(status_code=404, detail="Aucune configuration trouvée")
        
        config = config_data.data[0]
        
        return {
            "hotel_id": hotel_id,
            "configuration": config
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'export: {str(e)}")

# === ENDPOINTS DE VALIDATION DES DONNÉES ===

@router.get("/data-validation")
async def validate_hotel_data(
    hotel_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Valide les données de l'hôtel"""
    
    try:
        # Vérifier que l'utilisateur a accès à cet hôtel
        if not await validate_hotel_access(current_user["id"], hotel_id):
            raise HTTPException(status_code=403, detail="Accès refusé à cet hôtel")
        
        validation_results = {
            "hotel_id": hotel_id,
            "timestamp": datetime.now().isoformat(),
            "tariff_validation": {},
            "config_validation": {},
            "overall_status": "valid"
        }
        
        # Valider les données tarifaires
        tariff_data = await supabase.table("admin_tariff_plans").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").execute()
        
        if tariff_data.data:
            tariff_plan = tariff_data.data[0]
            plan_data = tariff_plan.get("plan_data", [])
            
            validation_results["tariff_validation"] = {
                "total_records": len(plan_data),
                "valid_records": 0,
                "invalid_records": 0,
                "missing_fields": [],
                "duplicate_rooms": set(),
                "issues": []
            }
            
            room_types = set()
            for i, record in enumerate(plan_data):
                if isinstance(record, dict):
                    # Vérifier les champs obligatoires
                    required_fields = ["room_type", "rate_plan", "price"]
                    missing_fields = [field for field in required_fields if field not in record]
                    
                    if missing_fields:
                        validation_results["tariff_validation"]["invalid_records"] += 1
                        validation_results["tariff_validation"]["missing_fields"].extend(missing_fields)
                        validation_results["tariff_validation"]["issues"].append(
                            f"Record {i}: champs manquants: {missing_fields}"
                        )
                    else:
                        validation_results["tariff_validation"]["valid_records"] += 1
                    
                    # Vérifier les doublons
                    room_type = record.get("room_type")
                    if room_type in room_types:
                        validation_results["tariff_validation"]["duplicate_rooms"].add(room_type)
                    room_types.add(room_type)
                    
                    # Vérifier les prix
                    try:
                        price = float(record.get("price", 0))
                        if price < 0:
                            validation_results["tariff_validation"]["issues"].append(
                                f"Record {i}: prix négatif: {price}"
                            )
                    except (ValueError, TypeError):
                        validation_results["tariff_validation"]["issues"].append(
                            f"Record {i}: prix invalide"
                        )
                else:
                    validation_results["tariff_validation"]["invalid_records"] += 1
                    validation_results["tariff_validation"]["issues"].append(
                        f"Record {i}: structure invalide"
                    )
        
        # Valider la configuration
        config_data = await supabase.table("admin_configuration").select("*").eq(
            "hotel_id", hotel_id
        ).eq("status", "active").execute()
        
        if config_data.data:
            config = config_data.data[0]
            config_data_dict = config.get("config_data", {})
            
            validation_results["config_validation"] = {
                "config_name": config.get("config_name"),
                "version": config.get("version"),
                "has_mapping": "mapping" in config_data_dict,
                "has_settings": "settings" in config_data_dict,
                "issues": []
            }
            
            # Valider la structure du mapping
            if "mapping" in config_data_dict:
                mapping = config_data_dict["mapping"]
                if not isinstance(mapping, dict):
                    validation_results["config_validation"]["issues"].append(
                        "Le mapping doit être un dictionnaire"
                    )
                    validation_results["overall_status"] = "invalid"
            
            # Valider la structure des settings
            if "settings" in config_data_dict:
                settings = config_data_dict["settings"]
                if not isinstance(settings, dict):
                    validation_results["config_validation"]["issues"].append(
                        "Les settings doivent être un dictionnaire"
                    )
                    validation_results["overall_status"] = "invalid"
        
        return validation_results
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la validation: {str(e)}")

# === ENDPOINTS D'HISTORIQUE ===

@router.get("/history/updates")
async def get_update_history(
    hotel_id: str,
    limit: int = 10,
    current_user: Dict = Depends(get_current_user)
):
    """Récupère l'historique des mises à jour pour l'hôtel"""
    
    try:
        # Vérifier que l'utilisateur a accès à cet hôtel
        if not await validate_hotel_access(current_user["id"], hotel_id):
            raise HTTPException(status_code=403, detail="Accès refusé à cet hôtel")
        
        # Récupérer l'historique des tarifs
        tariff_history = await supabase.table("admin_tariff_plans").select(
            "plan_name, upload_date, uploaded_by, status, file_name"
        ).eq("hotel_id", hotel_id).order("upload_date", desc=True).limit(limit).execute()
        
        # Récupérer l'historique des configurations
        config_history = await supabase.table("admin_configuration").select(
            "config_name, version, upload_date, uploaded_by, status, file_name"
        ).eq("hotel_id", hotel_id).order("upload_date", desc=True).limit(limit).execute()
        
        return {
            "hotel_id": hotel_id,
            "tariff_history": tariff_history.data if tariff_history.data else [],
            "config_history": config_history.data if config_history.data else [],
            "limit": limit
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")
