import os
from fastapi import FastAPI
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()

app = FastAPI()


class Shipment(Base):
    __tablename__ = "production"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String)
    receiver = Column(String)
    item = Column(String)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/test-db")
def test_db():
    return {"message": "DB connected successfully"}
