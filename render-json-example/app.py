import os
from datetime import datetime
from typing import Optional, List
from xml.etree import ElementTree as ET

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column
from fastapi import Body

SOAP_REQUEST_EXAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:t="http://example.com/tire">
  <soap:Body>
    <t:SendProductionRequest>
      <lot_no>LOT-20260303-001</lot_no>
      <line>L1</line>
      <tire_model>205/55R16</tire_model>
      <quantity>120</quantity>
      <note>Shift A</note>
    </t:SendProductionRequest>
  </soap:Body>
</soap:Envelope>
"""

@app.post(
    "/soap/productions",
    summary="SOAP(XML)로 생산정보 수신",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "text/xml": {
                    "schema": {"type": "string"},
                    "example": SOAP_REQUEST_EXAMPLE,
                },
                "application/xml": {
                    "schema": {"type": "string"},
                    "example": SOAP_REQUEST_EXAMPLE,
                },
            },
        }
    },
)
async def soap_send_production(xml_body: str = Body(..., media_type="text/xml")):
    raw = xml_body.encode("utf-8")

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

app = FastAPI(title="Tire Data Exchange Demo (REST+JSON + SOAP/XML)", version="1.0.0")


# =========================================================
# Production (DB)
# =========================================================
class Production(Base):
    __tablename__ = "production"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    lot_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    line: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    tire_model: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# -----------------------------
# REST(JSON) Schemas
# -----------------------------
class ProductionIn(BaseModel):
    lot_no: str = Field(..., examples=["LOT-20260303-001"])
    line: str = Field(..., examples=["L1"])
    tire_model: str = Field(..., examples=["205/55R16"])
    quantity: int = Field(..., ge=0, examples=[120])
    note: Optional[str] = Field(None, examples=["Shift A"])


class ProductionOut(ProductionIn):
    id: int
    produced_at: datetime


# -----------------------------
# Startup: 테이블 생성
# -----------------------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"ok": True}


# =========================================================
# 2) REST + JSON 엔드포인트
# =========================================================
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


# =========================================================
# 3) SOAP/XML 엔드포인트 (레거시 느낌 데모)
#    - POST /soap/productions
#    - XML(SOAP Envelope)로 생산정보를 받아서 DB에 저장하고
#      SOAP Response(XML)로 결과를 돌려줌
# =========================================================

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
TIRE_NS = "http://example.com/tire"  # 데모용 네임스페이스

ET.register_namespace("soap", SOAP_NS)
ET.register_namespace("t", TIRE_NS)


def _find_text_anywhere(root: ET.Element, tag_local_name: str) -> Optional[str]:
    """
    네임스페이스가 붙든 말든 <lot_no> 같은 로컬 태그명으로 값을 찾아줌
    """
    for elem in root.iter():
        if elem.tag.split("}")[-1] == tag_local_name:
            if elem.text is not None:
                return elem.text.strip()
            return ""
    return None


def _soap_fault(code: str, message: str) -> str:
    envelope = ET.Element(ET.QName(SOAP_NS, "Envelope"))
    body = ET.SubElement(envelope, ET.QName(SOAP_NS, "Body"))
    fault = ET.SubElement(body, "Fault")
    faultcode = ET.SubElement(fault, "faultcode")
    faultcode.text = code
    faultstring = ET.SubElement(fault, "faultstring")
    faultstring.text = message
    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _soap_success_response(record_id: int, produced_at: datetime) -> str:
    envelope = ET.Element(ET.QName(SOAP_NS, "Envelope"))
    body = ET.SubElement(envelope, ET.QName(SOAP_NS, "Body"))

    resp = ET.SubElement(body, ET.QName(TIRE_NS, "SendProductionResponse"))
    ET.SubElement(resp, "result").text = "OK"
    ET.SubElement(resp, "id").text = str(record_id)
    ET.SubElement(resp, "produced_at").text = produced_at.isoformat()

    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True).decode("utf-8")


@app.post("/soap/productions")
async def soap_send_production(request: Request):
    raw = await request.body()
    if not raw:
        xml = _soap_fault("Client", "Empty body")
        return Response(content=xml, media_type="text/xml", status_code=400)

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        xml = _soap_fault("Client", "Invalid XML")
        return Response(content=xml, media_type="text/xml", status_code=400)

    # 필수 필드 추출 (로컬 태그명 기준)
    lot_no = _find_text_anywhere(root, "lot_no")
    line = _find_text_anywhere(root, "line")
    tire_model = _find_text_anywhere(root, "tire_model")
    quantity_text = _find_text_anywhere(root, "quantity")
    note = _find_text_anywhere(root, "note")

    missing = [k for k, v in [
        ("lot_no", lot_no),
        ("line", line),
        ("tire_model", tire_model),
        ("quantity", quantity_text),
    ] if not v]

    if missing:
        xml = _soap_fault("Client", f"Missing fields: {', '.join(missing)}")
        return Response(content=xml, media_type="text/xml", status_code=400)

    try:
        quantity = int(quantity_text)
    except ValueError:
        xml = _soap_fault("Client", "quantity must be integer")
        return Response(content=xml, media_type="text/xml", status_code=400)

    # DB 저장
    db = SessionLocal()
    try:
        row = Production(
            lot_no=lot_no,
            line=line,
            tire_model=tire_model,
            quantity=quantity,
            note=note if note != "" else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        xml = _soap_success_response(row.id, row.produced_at)
        return Response(content=xml, media_type="text/xml", status_code=200)
    finally:
        db.close()
