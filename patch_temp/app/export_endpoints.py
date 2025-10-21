from fastapi import APIRouter, HTTPException, Body, Response
from typing import Any, Dict
from .export_utils import build_excel_bytes, build_pdf_bytes

router = APIRouter(prefix="/export", tags=["export"])

def _validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body is required.")
    kind = payload.get("kind") or "reservations"
    hotel_id = payload.get("hotel_id") or "unknown"
    rows = payload.get("rows") or payload.get("data") or []
    columns = payload.get("columns")
    metadata = payload.get("metadata") or {}
    return {"kind": kind, "hotel_id": hotel_id, "rows": rows, "columns": columns, "metadata": metadata}

@router.post("/excel")
def export_excel(payload: Dict[str, Any] = Body(...)):
    try:
        cfg = _validate_payload(payload)
        content = build_excel_bytes(**cfg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to build Excel: {e}")
    filename = f"{cfg['kind']}_{cfg['hotel_id']}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)

@router.post("/pdf")
def export_pdf(payload: Dict[str, Any] = Body(...)):
    try:
        cfg = _validate_payload(payload)
        content = build_pdf_bytes(**cfg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to build PDF: {e}")
    filename = f"{cfg['kind']}_{cfg['hotel_id']}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content, media_type="application/pdf", headers=headers)
