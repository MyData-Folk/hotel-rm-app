from fastapi import APIRouter, Query
from datetime import datetime

router = APIRouter(tags=["Monitoring"])

fake_hotels = [
    {"id": "folkestone", "name": "Folkestone Opera", "stars": 4},
    {"id": "vendome", "name": "Vendôme Opéra", "stars": 3},
    {"id": "washington", "name": "Washington Opéra", "stars": 4},
]

@router.get("/hotels")
def get_hotels():
    return {"count": len(fake_hotels), "hotels": fake_hotels}

@router.get("/files/status")
def files_status(hotel_id: str = Query(...)):
    return {
        "hotel_id": hotel_id,
        "files": [
            {"name": f"{hotel_id}_tarifs.xlsx", "status": "ok"},
            {"name": f"{hotel_id}_planning.xlsx", "status": "ok"},
        ],
        "checked": datetime.now().isoformat(),
    }

@router.post("/simulate")
def simulate(payload: dict):
    hotel = payload.get("hotel")
    arrival, departure = payload.get("arrival"), payload.get("departure")
    plan, category = payload.get("plan"), payload.get("category")
    total = 250.0  # Simulation fictive
    return {
        "hotel": hotel,
        "plan": plan,
        "category": category,
        "arrival": arrival,
        "departure": departure,
        "simulated_total": total,
    }
