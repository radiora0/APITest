import os
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# Render에서 sslmode가 URL에 포함되어 오는 경우가 많아서 그대로 사용하면 되는 편.
# 만약 SSL 관련 에러가 나면 DATABASE_URL 끝에 '?sslmode=require' 형태인지 확인. :contentReference[oaicite:4]{index=4}
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()
app = FastAPI(title="Tire Production JSON Exchange Demo", version="1.0.0")


class TireProductionIn(BaseModel):
    lot_no: str = Field(..., examples=["LOT-20260303-001"])
    line: str = Field(..., examples=["L1"])
    tire_model: str = Field(..., examples=["205/55R16"])
    quantity: int = Field(..., ge=0, examples=[120])
    qc_result: str = Field(..., examples=["PASS"])
    note: Optional[str] = Field(None, examples=["Shift A"])


class TireProductionOut(TireProductionIn):
    id: int
    produced_at: datetime


class TireProduction(Base):
    __tablename__ = "tire_production"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    lot_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    line: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    tire_model: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    qc_result: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


@app.on_event("startup")
def on_startup():
    # 데모용: 서버 시작 시 테이블 없으면 생성
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/tire-productions", response_model=TireProductionOut)
def create_record(payload: TireProductionIn):
    db = SessionLocal()
    try:
        row = TireProduction(**payload.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return TireProductionOut(
            id=row.id,
            produced_at=row.produced_at,
            **payload.model_dump(),
        )
    finally:
        db.close()


@app.get("/tire-productions/{record_id}", response_model=TireProductionOut)
def get_record(record_id: int):
    db = SessionLocal()
    try:
        row = db.get(TireProduction, record_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return TireProductionOut(
            id=row.id,
            produced_at=row.produced_at,
            lot_no=row.lot_no,
            line=row.line,
            tire_model=row.tire_model,
            quantity=row.quantity,
            qc_result=row.qc_result,
            note=row.note,
        )
    finally:
        db.close()


@app.get("/tire-productions")
def list_records(limit: int = 50):
    db = SessionLocal()
    try:
        rows: List[TireProduction] = (
            db.query(TireProduction)
            .order_by(TireProduction.id.desc())
            .limit(min(limit, 200))
            .all()
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
                    "qc_result": r.qc_result,
                    "note": r.note,
                }
                for r in rows
            ],
        }
    finally:
        db.close()
