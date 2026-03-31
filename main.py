"""
Caja Mágica — API de tesorería personal conversacional.
Backend FastAPI con persistencia JSON y clasificación NLP.
"""

import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from clasificador import clasificar
from excel_export import generar_excel

app = FastAPI(title="Caja Mágica", version="1.0.0")

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "movimientos.json"
DATA_FILE.parent.mkdir(exist_ok=True)

TASA_COP_USD: int = int(os.environ.get("TASA_COP_USD", 4200))
CAJA_MINIMA_COP: int = int(os.environ.get("CAJA_MINIMA_COP", 800_000))


# ─── Modelos ────────────────────────────────────────────────────────────────

class EntradaTexto(BaseModel):
    texto: str

class ConfigUpdate(BaseModel):
    tasa_cop_usd: Optional[int] = None
    caja_minima_cop: Optional[int] = None


# ─── Persistencia ───────────────────────────────────────────────────────────

def cargar_movimientos() -> list:
    """Lee movimientos desde disco. Retorna [] si no existe o hay error."""
    try:
        if DATA_FILE.exists():
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return []


def guardar_movimientos(lista: list) -> None:
    """Persiste la lista de movimientos en JSON."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(lista, f, indent=2, ensure_ascii=False)


def _mes_actual() -> str:
    return datetime.now().strftime("%Y-%m")


# ─── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/api/movimiento")
async def crear_movimiento(entrada: EntradaTexto):
    resultado = clasificar(entrada.texto)

    if resultado.error:
        return {"ok": False, "mensaje": resultado.error}

    movimiento = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "mes": _mes_actual(),
        "texto_original": entrada.texto,
        "tipo": resultado.tipo,
        "categoria": resultado.categoria,
        "descripcion": resultado.descripcion,
        "monto_cop": resultado.monto_cop,
        "monto_original": resultado.monto_original,
        "moneda": resultado.moneda,
        "es_proyeccion": resultado.es_proyeccion,
        "confianza": resultado.confianza,
    }

    movimientos = cargar_movimientos()
    movimientos.append(movimiento)
    guardar_movimientos(movimientos)

    return {"ok": True, "movimiento": movimiento, "mensaje": resultado.mensaje_respuesta}


@app.get("/api/movimientos")
async def listar_movimientos(
    mes: str = Query(default=None),
    tipo: Optional[str] = Query(default=None),
):
    mes = mes or _mes_actual()
    movimientos = cargar_movimientos()
    filtrado = [m for m in movimientos if m.get("mes") == mes]

    if tipo:
        filtrado = [m for m in filtrado if m.get("tipo") == tipo]

    filtrado.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return filtrado


@app.get("/api/resumen")
async def resumen(mes: str = Query(default=None)):
    global TASA_COP_USD, CAJA_MINIMA_COP
    mes = mes or _mes_actual()
    movimientos = cargar_movimientos()
    del_mes = [m for m in movimientos if m.get("mes") == mes]

    ingresos_cop = sum(m["monto_cop"] for m in del_mes if m.get("tipo") == "ingreso")
    egresos_cop = sum(m["monto_cop"] for m in del_mes if m.get("tipo") in ("egreso", "ahorro"))
    ahorros_cop = sum(m["monto_cop"] for m in del_mes if m.get("tipo") == "ahorro")
    neto = ingresos_cop - egresos_cop

    if len(del_mes) == 0:
        semaforo = "sin_datos"
    elif neto < CAJA_MINIMA_COP:
        semaforo = "rojo"
    elif neto < CAJA_MINIMA_COP * 2:
        semaforo = "amarillo"
    else:
        semaforo = "verde"

    mensajes_semaforo = {
        "sin_datos": "Sin movimientos aún",
        "rojo": "Caja por debajo del mínimo — revisa egresos",
        "amarillo": "Caja ajustada — monitorea esta semana",
        "verde": "Caja saludable — vas bien",
    }

    runway_meses = round(neto / (egresos_cop / 30), 1) if egresos_cop > 0 else 99

    por_categoria: dict[str, int] = {}
    for m in del_mes:
        cat = m.get("categoria", "otro")
        por_categoria[cat] = por_categoria.get(cat, 0) + m.get("monto_cop", 0)

    return {
        "mes": mes,
        "ingresos_cop": ingresos_cop,
        "egresos_cop": egresos_cop,
        "ahorros_cop": ahorros_cop,
        "neto_cop": neto,
        "semaforo": semaforo,
        "semaforo_mensaje": mensajes_semaforo.get(semaforo, ""),
        "runway_meses": runway_meses,
        "por_categoria": por_categoria,
        "total_movimientos": len(del_mes),
        "tasa_cop_usd": TASA_COP_USD,
        "caja_minima_cop": CAJA_MINIMA_COP,
    }


@app.delete("/api/movimiento/{mov_id}")
async def eliminar_movimiento(mov_id: str):
    movimientos = cargar_movimientos()
    original_len = len(movimientos)
    movimientos = [m for m in movimientos if m.get("id") != mov_id]

    if len(movimientos) == original_len:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")

    guardar_movimientos(movimientos)
    return {"ok": True, "eliminado": mov_id}


@app.get("/api/exportar")
async def exportar(mes: str = Query(default=None)):
    mes = mes or _mes_actual()
    movimientos = cargar_movimientos()
    del_mes = [m for m in movimientos if m.get("mes") == mes]
    path = generar_excel(del_mes, mes)

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"CajaMagica_{mes}.xlsx",
        headers={"Content-Disposition": f'attachment; filename="CajaMagica_{mes}.xlsx"'},
    )


@app.get("/api/config")
async def get_config():
    return {"tasa_cop_usd": TASA_COP_USD, "caja_minima_cop": CAJA_MINIMA_COP}


@app.post("/api/config")
async def update_config(cfg: ConfigUpdate):
    global TASA_COP_USD, CAJA_MINIMA_COP
    if cfg.tasa_cop_usd is not None:
        TASA_COP_USD = cfg.tasa_cop_usd
    if cfg.caja_minima_cop is not None:
        CAJA_MINIMA_COP = cfg.caja_minima_cop
    return {"tasa_cop_usd": TASA_COP_USD, "caja_minima_cop": CAJA_MINIMA_COP}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "mes_actual": _mes_actual()}


# ─── Static files (DEBE ir al final) ───────────────────────────────────────

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
