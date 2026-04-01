import os
import json
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Float, Boolean, Integer
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    # Fallback local persistence using SQLite for dev
    db_path = Path(__file__).parent / "data" / "caja.db"
    db_path.parent.mkdir(exist_ok=True)
    DATABASE_URL = f"sqlite:///{db_path}"

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class MovimientoDB(Base):
    __tablename__ = "movimientos"
    
    id = Column(String, primary_key=True, index=True)
    timestamp = Column(String, index=True)
    mes = Column(String, index=True)
    texto_original = Column(String)
    tipo = Column(String, index=True)
    categoria = Column(String, index=True)
    descripcion = Column(String)
    monto_cop = Column(Float)
    monto_original = Column(Float)
    moneda = Column(String)
    es_proyeccion = Column(Boolean, default=False)
    confianza = Column(Integer)

class ConfigDB(Base):
    __tablename__ = "config"
    id = Column(String, primary_key=True, default="global")
    tasa_cop_usd = Column(Integer)
    caja_minima_cop = Column(Integer)

Base.metadata.create_all(bind=engine)

def execute_migrations_if_needed():
    """Migrates existing JSON data to SQL exactly once."""
    json_file = Path(__file__).parent / "data" / "movimientos.json"
    if not json_file.exists():
        return
        
    with SessionLocal() as db:
        cnt = db.query(MovimientoDB).count()
        if cnt == 0:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    conf_map = {"alta": 100, "media": 50, "baja": 10}
                    for d in data:
                        raw_conf = d.get("confianza", 100)
                        if isinstance(raw_conf, str):
                            d["confianza"] = conf_map.get(raw_conf.lower(), 100)
                        mov = MovimientoDB(**d)
                        db.merge(mov)
                    db.commit()
            except Exception as e:
                print(f"Error migrating JSON data: {e}")
                db.rollback()
