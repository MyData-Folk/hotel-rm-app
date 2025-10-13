from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlmodel import Session
from typing import List, Dict, Any
from datetime import datetime, timedelta
import json
import os

from database import get_session
from models import User
from auth import get_current_user, check_hotel_permission

router = APIRouter()

DATA_DIR = "/app/data"

@router.post("/simulate", response_model=dict)
async def simulate(
    request_data: dict = Body(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Effectue une simulation tarifaire pour un hôtel spécifique"""
    hotel_id = request_data.get("hotel_id")
    room = request_data.get("room")
    plan = request_data.get("plan")
    start = request_data.get("start")
    end = request_data.get("end")
    partner_name = request_data.get("partner_name")
    apply_commission = request_data.get("apply_commission", True)
    apply_partner_discount = request_data.get("apply_partner_discount", True)
    promo_discount = request_data.get("promo_discount", 0.0)
    
    # Vérifier les permissions
    check_hotel_permission(hotel_id, current_user, session)
    
    # Validation des dates
    try:
        dstart = datetime.strptime(start, '%Y-%m-%d').date()
        dend = datetime.strptime(end, '%Y-%m-%d').date()
        
        if dstart >= dend:
            raise HTTPException(status_code=400, detail="La date de début doit être avant la date de fin")
    except ValueError:
        raise HTTPException(status_code=400, detail="Format de date invalide. Utilisez YYYY-MM-DD")
    
    # Récupération des données
    try:
        data_path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')
        config_path = os.path.join(DATA_DIR, f'{hotel_id}_config.json')
        
        if not os.path.exists(data_path):
            raise HTTPException(status_code=404, detail=f"Données de planning introuvables pour '{hotel_id}'")
        
        if not os.path.exists(config_path):
            raise HTTPException(status_code=404, detail=f"Configuration introuvable pour '{hotel_id}'")
        
        with open(data_path, 'r', encoding='utf-8') as f:
            hotel_data = json.load(f)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            hotel_config = json.load(f)
        
        room_data = hotel_data.get("rooms", {}).get(room)
        if not room_data:
            raise HTTPException(status_code=404, detail=f"Chambre '{room}' introuvable.")
        
        # Recherche du plan tarifaire
        plan_data = room_data.get("plans", {}).get(plan)
        partner_info = hotel_config.get("partners", {}).get(partner_name, {})
        
        # Si plan non trouvé directement, chercher via les codes partenaires
        if not plan_data and partner_info and partner_name:
            partner_codes = partner_info.get("codes", [])
            for p_name, p_data in room_data.get("plans", {}).items():
                if any(code.lower() in p_name.lower() for code in partner_codes):
                    plan_key, plan_data = p_name, p_data
                    break
        
        if not plan_data:
            available_plans = list(room_data.get("plans", {}).keys())
            raise HTTPException(
                status_code=404, 
                detail=f"Plan tarifaire '{plan}' introuvable. Plans disponibles: {available_plans[:10]}"
            )
        
        # Configuration des calculs
        commission_rate = partner_info.get("commission", 0) / 100.0 if apply_commission else 0.0
        discount_info = partner_info.get("defaultDiscount", {})
        partner_discount_rate = discount_info.get("percentage", 0) / 100.0 if apply_partner_discount else 0.0
        promo_discount_rate = promo_discount / 100.0
        
        # Vérification si le plan est exclu de la remise partenaire
        apply_partner_discount = request_data.get("apply_partner_discount", True)
        if apply_partner_discount and discount_info.get("excludePlansContaining"):
            exclude_keywords = discount_info.get("excludePlansContaining", [])
            if any(kw.lower() in plan.lower() for kw in exclude_keywords):
                apply_partner_discount = False
                partner_discount_rate = 0.0
        
        # Calculs par date
        results = []
        current_date = dstart
        
        while current_date < dend:
            date_key = current_date.strftime("%Y-%m-%d")
            gross_price = plan_data.get(date_key)
            stock = room_data.get("stock", {}).get(date_key, 0)
            
            # Application des remises en cascade
            price_after_partner_discount = gross_price
            if gross_price is not None and apply_partner_discount and partner_discount_rate > 0:
                price_after_partner_discount = gross_price * (1 - partner_discount_rate)
            
            price_after_promo = price_after_partner_discount
            if gross_price is not None and promo_discount_rate > 0:
                price_after_promo = price_after_partner_discount * (1 - promo_discount_rate)
            
            # Calcul de la commission
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
        
        return {
            "simulation_info": {
                "room": room,
                "plan": plan,
                "partner": partner_name,
                "partner_commission": commission_rate * 100,
                "partner_discount": partner_discount_rate * 100,
                "promo_discount": promo_discount,
                "apply_partner_discount": apply_partner_discount,
                "start_date": start,
                "end_date": end,
                "nights": len(results),
                "source": hotel_data.get("report_generated_at", "Source inconnue")
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
        raise HTTPException(status_code=500, detail=f"Erreur lors de la simulation: {str(e)}")

@router.get("/plans/partner", response_model=dict)
async def get_plans_by_partner(
    hotel_id: str = Query(...),
    partner_name: str = Query(...),
    room_type: str = Query(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Récupère les plans tarifaires disponibles pour un partenaire et une chambre spécifiques"""
    # Vérifier les permissions
    check_hotel_permission(hotel_id, current_user, session)
    
    try:
        # Charger les données
        data_path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')
        config_path = os.path.join(DATA_DIR, f'{hotel_id}_config.json')
        
        if not os.path.exists(data_path):
            raise HTTPException(status_code=404, detail=f"Données de planning introuvables pour '{hotel_id}'")
        
        if not os.path.exists(config_path):
            raise HTTPException(status_code=404, detail=f"Configuration introuvable pour '{hotel_id}'")
        
        with open(data_path, 'r', encoding='utf-8') as f:
            hotel_data = json.load(f)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            hotel_config = json.load(f)
        
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
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des plans: {str(e)}")

@router.post("/availability", response_model=dict)
async def get_availability(
    request_data: dict = Body(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Récupère les disponibilités pour une période donnée"""
    hotel_id = request_data.get("hotel_id")
    start_date = request_data.get("start_date")
    end_date = request_data.get("end_date")
    room_types = request_data.get("room_types", [])
    
    # Vérifier les permissions
    check_hotel_permission(hotel_id, current_user, session)
    
    try:
        # Validation des dates
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        if start_date_obj >= end_date_obj:
            raise HTTPException(status_code=400, detail="La date de début doit être avant la date de fin")

        # Charger les données
        data_path = os.path.join(DATA_DIR, f'{hotel_id}_data.json')
        
        if not os.path.exists(data_path):
            raise HTTPException(status_code=404, detail=f"Données de planning introuvables pour '{hotel_id}'")
        
        with open(data_path, 'r', encoding='utf-8') as f:
            hotel_data_full = json.load(f)
        
        hotel_data = hotel_data_full.get("rooms", {})
        
        # Filtrer les chambres si spécifié
        room_types = room_types if room_types else list(hotel_data.keys())
        
        # Générer toutes les dates de la période
        dates_in_period = []
        current_date = start_date_obj
        while current_date < end_date_obj:
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
        
        return {
            "hotel_id": hotel_id,
            "period": {
                "start_date": start_date,
                "end_date": end_date,
                "dates": dates_in_period,
                "date_display": date_display
            },
            "availability": availability_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul des disponibilités: {str(e)}")