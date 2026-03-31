"""
Motor NLP de clasificación financiera para Caja Mágica.
Clasifica texto libre en movimientos financieros tipados
usando regex + heurísticas. Sin dependencias externas.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

TASA_COP_USD: int = 4200


@dataclass
class ResultadoClasificacion:
    """Resultado estructurado de la clasificación de un texto financiero."""
    tipo: str = ""                    # ingreso|egreso|ahorro|proyeccion
    categoria: str = ""
    descripcion: str = ""
    monto_cop: int = 0
    monto_original: float = 0.0
    moneda: str = "COP"              # COP|USD
    es_proyeccion: bool = False
    mensaje_respuesta: str = ""
    confianza: str = "alta"          # alta|media|baja
    error: Optional[str] = None


# ─── Reglas de clasificación ordenadas por prioridad ────────────────────────

_REGLAS: list[dict] = [
    {
        "nombre": "ahorro_ibkr",
        "pattern": r"ibkr|etf|s&p|qqqm|iaum|inversi[oó]n a largo|mercado de valores|acciones",
        "tipo": "ahorro",
        "categoria": "ibkr",
        "mensaje": "Registrado como ahorro IBKR. No toca la caja operativa — buen hábito.",
    },
    {
        "nombre": "ahorro_nu",
        "pattern": r"\bnu\b|cajita|cajitas|fondo nu|ahorro nu|nubank",
        "tipo": "ahorro",
        "categoria": "nu",
        "mensaje": "Anotado en cajitas Nu. Fondo de emergencia creciendo.",
    },
    {
        "nombre": "proyeccion_freelance",
        "pattern": r"voy a facturar|espero cobrar|espero facturar|pr[oó]ximo cliente|estimado de|proyecto pendiente de pago|cliente me va a pagar",
        "tipo": "proyeccion",
        "categoria": "freelance",
        "es_proyeccion": True,
        "mensaje": "Proyección de servicios anotada. Actualiza cuando el pago llegue.",
    },
    {
        "nombre": "proyeccion_ventas_digitales",
        "pattern": r"voy a vender|espero vender|proyecci[oó]n de venta|plantilla pendiente|producto pendiente",
        "tipo": "proyeccion",
        "categoria": "ventas_digitales",
        "es_proyeccion": True,
        "mensaje": "Proyección de venta digital anotada.",
    },
    {
        "nombre": "proyeccion_general",
        "pattern": r"voy a|espero recibir|pr[oó]ximo mes|siguiente mes",
        "tipo": "proyeccion",
        "categoria": "otro",
        "es_proyeccion": True,
        "mensaje": "Proyección registrada. Confirma cuando sea real.",
    },
    {
        "nombre": "ingreso_mesada",
        "pattern": r"pap[aá]|mam[aá]|papa|mama|padres|familia|mesada|mandaron|pasaron|transfirieron|depositaron|me dieron|me mandaron",
        "tipo": "ingreso",
        "categoria": "mesada",
        "mensaje": "Ingreso familiar registrado.",
    },
    {
        "nombre": "ingreso_freelance",
        "pattern": r"factur[eé]|cobr[eé]|cliente pag[oó]|consultor[ií]a|freelance|servicio|proyecto entregado|contrato",
        "tipo": "ingreso",
        "categoria": "freelance",
        "mensaje": "Ingreso por servicios registrado.",
    },
    {
        "nombre": "ingreso_ventas_digitales",
        "pattern": r"plantilla|vend[ií]|venta digital|producto digital|template|tienda|ecommerce",
        "tipo": "ingreso",
        "categoria": "ventas_digitales",
        "mensaje": "Venta digital registrada.",
    },
    {
        "nombre": "egreso_tarjeta",
        "pattern": r"tarjeta|bancolombia|\btc\b|cr[eé]dito|pago de tarjeta",
        "tipo": "egreso",
        "categoria": "tc_pago",
        "mensaje": "Pago de tarjeta registrado. Bien hecho pagarlo completo — así se construye historial sin pagar intereses.",
    },
    {
        "nombre": "egreso_alimentacion",
        "pattern": r"almuerzo|comida|mercado|restaurante|desayuno|cena|snack|domicilio|rappi|caf[eé]|tinto",
        "tipo": "egreso",
        "categoria": "alimentacion",
        "mensaje": "Gasto de alimentación registrado.",
    },
    {
        "nombre": "egreso_transporte",
        "pattern": r"bus|transporte|uber|taxi|metro|gasolina|parqueadero",
        "tipo": "egreso",
        "categoria": "transporte",
        "mensaje": "Gasto de transporte registrado.",
    },
    {
        "nombre": "egreso_general",
        "pattern": r"gast[eé]|pagu[eé]|compr[eé]|gasto|egreso|costo",
        "tipo": "egreso",
        "categoria": "otro",
        "mensaje": "Egreso registrado.",
    },
]


def _extraer_monto(texto: str) -> tuple[float, str]:
    """
    Extrae monto y moneda del texto.
    Retorna (monto, moneda). monto=0 si no se encuentra.
    Orden de prioridad según spec.
    """
    t = texto.lower().replace(",", ".")

    # 1. USD con sufijo: 25 usd, 25 dólares
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:usd|d[oó]lares|dolares|dolar|d[oó]lar)", t)
    if m:
        return float(m.group(1)), "USD"

    # 2. USD con prefijo $: $25 usd
    m = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:usd|dolares|d[oó]lares)", t)
    if m:
        return float(m.group(1)), "USD"

    # 3. COP millones: 1.5 millones
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:millones?|millon)", t)
    if m:
        return float(m.group(1)) * 1_000_000, "COP"

    # 4. COP miles k/mil: 900k, 40 mil
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:k|mil)\b", t)
    if m:
        return float(m.group(1)) * 1_000, "COP"

    # 5. COP formato colombiano: $900.000
    m = re.search(r"\$\s*(\d{1,3}(?:\.\d{3})+)", t)
    if m:
        valor_str = m.group(1).replace(".", "")
        return float(valor_str), "COP"

    # 6. COP plano con pesos: 900.000 pesos
    m = re.search(r"(\d{1,3}(?:\.\d{3})+)\s*(?:pesos?|cop)?", t)
    if m:
        valor_str = m.group(1).replace(".", "")
        return float(valor_str), "COP"

    # 7. COP número largo sin sufijo: 900000
    m = re.search(r"\b(\d{4,})\b", t)
    if m:
        return float(m.group(1)), "COP"

    return 0, "COP"


def clasificar(texto: str) -> ResultadoClasificacion:
    """
    Clasifica un texto libre en un movimiento financiero.

    Args:
        texto: Texto en lenguaje natural describiendo un movimiento.

    Returns:
        ResultadoClasificacion con todos los campos poblados.
    """
    texto_limpio = texto.strip()
    if not texto_limpio:
        return ResultadoClasificacion(
            error="Escribe un poco más. Ejemplo: 'gasté 45k en almuerzo' o 'mis papás me pasaron 800k'."
        )

    monto, moneda = _extraer_monto(texto_limpio)

    # Calcular monto en COP
    if moneda == "USD" and monto > 0:
        monto_cop = round(monto * TASA_COP_USD)
    else:
        monto_cop = round(monto)

    # Evaluar reglas en orden de prioridad
    texto_lower = texto_limpio.lower()
    for regla in _REGLAS:
        if re.search(regla["pattern"], texto_lower):
            if monto <= 0:
                return ResultadoClasificacion(
                    error="No encontré el monto. Ejemplo: 'mis papás me pasaron 900k' o 'consultoría $25 USD'."
                )
            return ResultadoClasificacion(
                tipo=regla["tipo"],
                categoria=regla["categoria"],
                descripcion=texto_limpio,
                monto_cop=monto_cop,
                monto_original=monto,
                moneda=moneda,
                es_proyeccion=regla.get("es_proyeccion", False),
                mensaje_respuesta=regla["mensaje"],
                confianza="alta",
            )

    # Fallback con monto
    if monto > 0:
        return ResultadoClasificacion(
            tipo="egreso",
            categoria="otro",
            descripcion=texto_limpio,
            monto_cop=monto_cop,
            monto_original=monto,
            moneda=moneda,
            es_proyeccion=False,
            mensaje_respuesta="Registré el monto pero no pude clasificar bien. ¿Es un ingreso o egreso? Intenta ser más específico.",
            confianza="baja",
        )

    # Fallback sin monto
    return ResultadoClasificacion(
        error="Escribe un poco más. Ejemplo: 'gasté 45k en almuerzo' o 'mis papás me pasaron 800k'."
    )
