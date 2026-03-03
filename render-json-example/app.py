from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Dict
import uuid
import time

app = FastAPI(title="Render JSON Example", version="1.0.0")

# 데모용 "메모리 DB" (배포 후 재시작되면 데이터 날아감)
DB: Dict[str, dict] = {}


class ShipmentCreate(BaseModel):
    sender: str = Field(..., examples=["홍길동"])
    receiver: str = Field(..., examples=["김철수"])
    address: str = Field(..., examples=["서울특별시 ..."])
    item: str = Field(..., examples=["노트북"])
    note: str | None = Field(None, examples=["문 앞에 두세요"])


class Shipment(BaseModel):
    id: str
    created_at: int
    sender: str
    receiver: str
    address: str
    item: str
    note: str | None


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/shipments", response_model=Shipment)
def create_shipment(payload: ShipmentCreate):
    shipment_id = str(uuid.uuid4())
    created_at = int(time.time())

    shipment = {
        "id": shipment_id,
        "created_at": created_at,
        **payload.model_dump(),
    }
    DB[shipment_id] = shipment
    return shipment


@app.get("/shipments/{shipment_id}", response_model=Shipment)
def get_shipment(shipment_id: str):
    shipment = DB.get(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


@app.get("/shipments")
def list_shipments():
    # 단순 리스트
    return {"count": len(DB), "items": list(DB.values())}
