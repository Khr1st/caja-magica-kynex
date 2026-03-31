"""
Caja Mágica — API de tesorería personal conversacional.
Backend FastAPI con persistencia JSON, clasificación NLP,
y auto-sincronización Excel en tiempo real.
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

app = FastAPI(title="Caja Mágica", version="1.1.0")

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "movimientos.json"
DATA_FILE.parent.mkdir(exist_ok=True)

TASA_COP_USD: int = int(os.environ.get("TASA_COP_USD", 4200))
CAJA_MINIMA_COP: int = int(os.environ.get("CAJA_MINIMA_COP", 800_000))


# ─── Modelos ────────────────────────────────────────────────────────────────

class EntradaTexto(BaseModel):
    texto: str
    moneda_forzada: Optional[str] = None  # 'COP' | 'USD'

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


def _sync_excel(mes: str | None = None) -> None:
    """Auto-regenera el Excel cada vez que hay un cambio en movimientos."""
    mes = mes or _mes_actual()
    movimientos = cargar_movimientos()
    del_mes = [m for m in movimientos if m.get("mes") == mes]
    try:
        generar_excel(del_mes, mes)
    except Exception:
        pass  # Non-critical — no debe bloquear la operación principal


# ─── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/api/movimiento")
async def crear_movimiento(entrada: EntradaTexto):
    resultado = clasificar(entrada.texto, moneda_forzada=entrada.moneda_forzada)

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
    _sync_excel()

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
    _sync_excel()
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


@app.get("/api/analytics")
async def analytics(mes: str = Query(default=None)):
    """Datos estructurados para gráficos gráficos y radar separados por tipo."""
    mes = mes or _mes_actual()
    movimientos = cargar_movimientos()
    del_mes = [m for m in movimientos if m.get("mes") == mes]

    # Por tipo (para barras)
    por_tipo: dict[str, int] = {}
    ing_por_cat: dict[str, int] = {}
    egr_por_cat: dict[str, int] = {}

    for m in del_mes:
        t = m.get("tipo", "otro")
        monto = m.get("monto_cop", 0)
        cat = m.get("categoria", "otro")
        
        por_tipo[t] = por_tipo.get(t, 0) + monto
        
        if t == "ingreso":
            ing_por_cat[cat] = ing_por_cat.get(cat, 0) + monto
        elif t == "egreso":
            egr_por_cat[cat] = egr_por_cat.get(cat, 0) + monto

    # Tendencia diaria acumulada (para gráfico de líneas)
    daily: dict[str, dict[str, int]] = {}
    for m in sorted(del_mes, key=lambda x: x.get("timestamp", "")):
        ts = m.get("timestamp", "")
        day = ts[:10] if len(ts) >= 10 else "unknown"
        if day not in daily:
            daily[day] = {"ingresos": 0, "egresos": 0}
        if m.get("tipo") == "ingreso":
            daily[day]["ingresos"] += m.get("monto_cop", 0)
        elif m.get("tipo") in ("egreso", "ahorro"):
            daily[day]["egresos"] += m.get("monto_cop", 0)

    # Convertir a series para Chart.js
    dias = sorted(daily.keys())
    ingresos_diarios = [daily[d]["ingresos"] for d in dias]
    egresos_diarios = [daily[d]["egresos"] for d in dias]

    # Acumulado
    acumulado = []
    running = 0
    for d in dias:
        running += daily[d]["ingresos"] - daily[d]["egresos"]
        acumulado.append(running)

    # Proyecciones
    proyecciones = [m for m in del_mes if m.get("es_proyeccion")]
    proy_por_cat: dict[str, int] = {}
    proy_total = 0
    for m in proyecciones:
        cat = m.get("categoria", "otro")
        monto = m.get("monto_cop", 0)
        is_egreso = m.get("tipo") == "proyeccion_egreso"
        monto_sgn = -monto if is_egreso else monto
        
        proy_por_cat[cat] = proy_por_cat.get(cat, 0) + monto_sgn
        proy_total += monto_sgn

    # Radar de categorías (todas)
    todas_cats = list(set(list(ing_por_cat.keys()) + list(egr_por_cat.keys())))

    # Combinado general para la leyenda de resumen
    por_categoria = {c: ing_por_cat.get(c, 0) + egr_por_cat.get(c, 0) for c in todas_cats}

    return {
        "mes": mes,
        "por_tipo": por_tipo,
        "por_categoria": por_categoria,
        "egresos_por_categoria": egr_por_cat,
        "tendencia": {
            "dias": dias,
            "ingresos": ingresos_diarios,
            "egresos": egresos_diarios,
            "acumulado": acumulado,
        },
        "proyecciones": {
            "lista": proyecciones,
            "por_categoria": proy_por_cat,
            "total": proy_total,
            "count": len(proyecciones),
        },
        "radar": {
            "categorias": todas_cats,
            "ingresos": [ing_por_cat.get(c, 0) for c in todas_cats],
            "egresos": [egr_por_cat.get(c, 0) for c in todas_cats],
        },
        "total_movimientos": len(del_mes),
    }


@app.get("/api/meses")
async def listar_meses():
    """Lista todos los meses que tienen movimientos, para el selector de mes."""
    movimientos = cargar_movimientos()
    meses = sorted(set(m.get("mes", "") for m in movimientos if m.get("mes")), reverse=True)
    if not meses or _mes_actual() not in meses:
        meses.insert(0, _mes_actual())
    return meses


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
    return {"status": "ok", "version": "1.1.0", "mes_actual": _mes_actual()}


# ─── Static files (DEBE ir al final) ───────────────────────────────────────

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
