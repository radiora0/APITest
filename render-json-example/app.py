import os
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column


# -----------------------------
# DB 연결 (Render DATABASE_URL + pg8000)
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in Render Environment Variables")

# Render가 주는 URL 스킴을 pg8000용 SQLAlchemy URL로 변환
# 예) postgresql://...  -> postgresql+pg8000://...
# 예) postgres://...    -> postgresql+pg8000://...
db_url = DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

engine = create_engine(db_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


# -----------------------------
# FastAPI
# -----------------------------
app = FastAPI(title="Tire Production JSON Exchange Demo", version="1.0.0")


# -----------------------------
# Pydantic Schemas (JSON 입출력)
# -----------------------------
class ProductionIn(BaseModel):
    lot_no: str = Field(..., examples=["LOT-20260303-001"])
    line: str = Field(..., examples=["L1"])
    tire_model: str = Field(..., examples=["205/55R16"])
    quantity: int = Field(..., ge=0, examples=[120])
    qc_result: str = Field(..., examples=["PASS"])  # PASS / FAIL 등
    note: Optional[str] = Field(None, examples=["Shift A"])


class ProductionOut(ProductionIn):
    id: int
    produced_at: datetime


# -----------------------------
# SQLAlchemy Model (DB 테이블)
# -----------------------------
class Production(Base):
    __tablename__ = "production"  # <- 네가 정한 테이블명

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    lot_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    line: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    tire_model: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    qc_result: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# -----------------------------
# 앱 시작 시 테이블 생성 (없으면 생성)
# -----------------------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


# -----------------------------
# Routes
# -----------------------------
@app.get("/health")
def health():
    return {"ok": True}


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
            qc_result=row.qc_result,
            note=row.note,
        )
    finally:
        db.close()


@app.get("/productions")
def list_productions(limit: int = 50):
    db = SessionLocal()
    try:
        rows: List[Production] = (
            db.query(Production)
            .order_by(Production.id.desc())
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
