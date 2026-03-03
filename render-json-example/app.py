import os
from datetime import datetime
from typing import Optional, List, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column


# -----------------------------
# DB 연결 (Render DATABASE_URL + pg8000)
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

db_url = DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

engine = create_engine(db_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

app = FastAPI(title="Tire Data Exchange Demo", version="1.0.0")


# =========================================================
# 1) 생산정보 (production)
# =========================================================
class ProductionIn(BaseModel):
    lot_no: str = Field(..., examples=["LOT-20260303-001"])
    line: str = Field(..., examples=["L1"])
    tire_model: str = Field(..., examples=["205/55R16"])
    quantity: int = Field(..., ge=0, examples=[120])
    note: Optional[str] = Field(None, examples=["Shift A"])


class ProductionOut(ProductionIn):
    id: int
    produced_at: datetime


class Production(Base):
    __tablename__ = "production"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    lot_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    line: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    tire_model: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# =========================================================
# 2) 입출고 실적 (inventory_movement)
#    - 입고/출고를 movement_type으로 구분
# =========================================================
class InventoryMovementIn(BaseModel):
    movement_type: Literal["IN", "OUT"] = Field(..., examples=["IN"])
    warehouse: str = Field(..., examples=["WH-A"])
    tire_model: str = Field(..., examples=["205/55R16"])
    quantity: int = Field(..., ge=0, examples=[60])
    reference_no: Optional[str] = Field(None, examples=["SHIP-20260303-009"])
    note: Optional[str] = Field(None, examples=["customer delivery"])


class InventoryMovementOut(InventoryMovementIn):
    id: int
    moved_at: datetime


class InventoryMovement(Base):
    __tablename__ = "inventory_movement"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    moved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    movement_type: Mapped[str] = mapped_column(String(8), index=True, nullable=False)  # IN / OUT
    warehouse: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    tire_model: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_no: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# =========================================================
# 3) 검사정보 (inspection)
# =========================================================
class InspectionIn(BaseModel):
    lot_no: str = Field(..., examples=["LOT-20260303-001"])
    tire_model: str = Field(..., examples=["205/55R16"])
    inspector: str = Field(..., examples=["Kim"])
    qc_result: Literal["PASS", "FAIL"] = Field(..., examples=["PASS"])
    defect_code: Optional[str] = Field(None, examples=["BUBBLE"])
    note: Optional[str] = Field(None, examples=["minor issue"])


class InspectionOut(InspectionIn):
    id: int
    inspected_at: datetime


class Inspection(Base):
    __tablename__ = "inspection"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inspected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    lot_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    tire_model: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    inspector: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    qc_result: Mapped[str] = mapped_column(String(16), index=True, nullable=False)  # PASS/FAIL
    defect_code: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# -----------------------------
# Startup: 테이블 생성
# -----------------------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"ok": True}


# -----------------------------
# 생산정보 API
# -----------------------------
@app.post("/productions", response_model=ProductionOut)
def create_production(payload: ProductionIn):
    db = SessionLocal()
    try:
        row = Production(**payload.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return ProductionOut(
            id=row.id,
            produced_at=row.produced_at,
            **payload.model_dump(),
        )
    finally:
        db.close()


@app.get("/productions/{record_id}", response_model=ProductionOut)
def get_production(record_id: int):
    db = SessionLocal()
    try:
        row = db.get(Production, record_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return ProductionOut(
            id=row.id,
            produced_at=row.produced_at,
            lot_no=row.lot_no,
            line=row.line,
            tire_model=row.tire_model,
            quantity=row.quantity,
            note=row.note,
        )
    finally:
        db.close()


@app.get("/productions")
def list_productions(limit: int = 50):
    db = SessionLocal()
    try:
        rows: List[Production] = (
            db.query(Production).order_by(Production.id.desc()).limit(min(limit, 200)).all()
        )
        return {
            "count": len(rows),
            "items": [
                {
                    "id": r.id,
                    "produced_at": r.produced_at,
                    "lot_no": r.lot_no,
                    "line": r.line,
                    "tire_model": r.tire_model,
                    "quantity": r.quantity,
                    "note": r.note,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


# -----------------------------
# 입출고 실적 API
# -----------------------------
@app.post("/inventory-movements", response_model=InventoryMovementOut)
def create_inventory_movement(payload: InventoryMovementIn):
    db = SessionLocal()
    try:
        row = InventoryMovement(**payload.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return InventoryMovementOut(
            id=row.id,
            moved_at=row.moved_at,
            **payload.model_dump(),
        )
    finally:
        db.close()


@app.get("/inventory-movements/{record_id}", response_model=InventoryMovementOut)
def get_inventory_movement(record_id: int):
    db = SessionLocal()
    try:
        row = db.get(InventoryMovement, record_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return InventoryMovementOut(
            id=row.id,
            moved_at=row.moved_at,
            movement_type=row.movement_type,  # IN/OUT
            warehouse=row.warehouse,
            tire_model=row.tire_model,
            quantity=row.quantity,
            reference_no=row.reference_no,
            note=row.note,
        )
    finally:
        db.close()


@app.get("/inventory-movements")
def list_inventory_movements(limit: int = 50):
    db = SessionLocal()
    try:
        rows: List[InventoryMovement] = (
            db.query(InventoryMovement).order_by(InventoryMovement.id.desc()).limit(min(limit, 200)).all()
        )
        return {
            "count": len(rows),
            "items": [
                {
                    "id": r.id,
                    "moved_at": r.moved_at,
                    "movement_type": r.movement_type,
                    "warehouse": r.warehouse,
                    "tire_model": r.tire_model,
                    "quantity": r.quantity,
                    "reference_no": r.reference_no,
                    "note": r.note,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


# -----------------------------
# 검사정보 API
# -----------------------------
@app.post("/inspections", response_model=InspectionOut)
def create_inspection(payload: InspectionIn):
    db = SessionLocal()
    try:
        row = Inspection(**payload.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return InspectionOut(
            id=row.id,
            inspected_at=row.inspected_at,
            **payload.model_dump(),
        )
    finally:
        db.close()


@app.get("/inspections/{record_id}", response_model=InspectionOut)
def get_inspection(record_id: int):
    db = SessionLocal()
    try:
        row = db.get(Inspection, record_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return InspectionOut(
            id=row.id,
            inspected_at=row.inspected_at,
            lot_no=row.lot_no,
            tire_model=row.tire_model,
            inspector=row.inspector,
            qc_result=row.qc_result,
            defect_code=row.defect_code,
            note=row.note,
        )
    finally:
        db.close()


@app.get("/inspections")
def list_inspections(limit: int = 50):
    db = SessionLocal()
    try:
        rows: List[Inspection] = (
            db.query(Inspection).order_by(Inspection.id.desc()).limit(min(limit, 200)).all()
        )
        return {
            "count": len(rows),
            "items": [
                {
                    "id": r.id,
                    "inspected_at": r.inspected_at,
                    "lot_no": r.lot_no,
                    "tire_model": r.tire_model,
                    "inspector": r.inspector,
                    "qc_result": r.qc_result,
                    "defect_code": r.defect_code,
                    "note": r.note,
                }
                for r in rows
            ],
        }
    finally:
        db.close()
