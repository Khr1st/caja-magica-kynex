"""
Motor NLP de clasificación financiera para Caja Mágica.
Clasifica texto libre en movimientos financieros tipados
usando regex + heurísticas. Sin dependencias externas.
"""

import re
from dataclasses import dataclass
from typing import Optional

TASA_COP_USD: int = 4200


@dataclass
class ResultadoClasificacion:
    """Resultado estructurado de la clasificación de un texto financiero."""
    tipo: str = ""                    # ingreso|egreso|ahorro|proyeccion_ingreso|proyeccion_egreso
    categoria: str = ""
    descripcion: str = ""
    monto_cop: int = 0
    monto_original: float = 0.0
    moneda: str = "COP"              # COP|USD
    es_proyeccion: bool = False
    mensaje_respuesta: str = ""
    confianza: str = "alta"          # alta|media|baja
    error: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
#  MOTOR DE DETECCIÓN DE PROYECCIONES
#  Sistema de señales multi-capa para identificar movimientos futuros/pendientes.
#  Cada capa cubre una clase distinta de evidencia lingüística.
# ══════════════════════════════════════════════════════════════════════════════

# ── Capa 1: Perífrasis verbales de futuro (ir a + inf, tener que + inf, etc.) ──
_CAPA_MODAL = re.compile(
    r"\bvoy a\b|\bvamos a\b|\bvan a\b|\bva a\b|"
    r"\btengo que\b|\btienes que\b|\btiene que\b|\btenemos que\b|"
    r"\bhay que\b|"
    r"\bme toca\b|\bte toca\b|\btoca (?:pagar|cobrar|facturar|renovar|comprar|transferir)\b|"
    r"\bdebo (?:pagar|cobrar|facturar|transferir|abonar|saldar)\b|"
    r"\bnecesito (?:pagar|cobrar|transferir|abonar)\b|"
    r"\bplaneo\b|\bpienso\b(?=.{0,50}(?:\d|pagar|cobrar|facturar|invertir))|"
    r"\bquiero (?:pagar|cobrar|ahorrar|invertir|comprar|transferir)\b|"
    r"\bme falta (?:pagar|cobrar)\b|\bme quedan? (?:pagar|cobrar)\b|"
    r"\bpienso (?:pagar|cobrar|facturar|invertir)\b",
    re.IGNORECASE,
)

# ── Capa 2: Verbos de expectativa, estimación o incertidumbre ──
_CAPA_ESPERA = re.compile(
    r"\bespero (?:recibir|cobrar|facturar|pagar|ganar|vender|que me paguen)\b|"
    r"\bcalculo(?: que)?\b(?=.{0,60}(?:\d|k\b|pesos|usd|lucas|cobrar|pagar))|"
    r"\bestimo(?: que)?\b(?=.{0,60}(?:\d|k\b|pesos|usd|lucas))|"
    r"\bcreo que\b(?=.{0,60}(?:\d|k\b|pesos|usd|lucas|cobrar|pagar|me van|van a))|"
    r"\bsupongo que\b(?=.{0,60}(?:\d|k\b|pesos|usd))|"
    r"\bdeber[ií]a (?:llegar|pagar|cobrar|recibir|entrar)\b|"
    r"\baproximadamente\b|\balrededor de\b|"
    r"\bunos\b(?=.{0,20}(?:\d+\s*(?:k\b|mil\b|lucas\b|pesos\b|usd\b|millones?\b|palos?\b)))|"
    r"\bcomo\b(?=.{0,15}(?:\d+\s*(?:k\b|mil\b|lucas\b|pesos\b)))",
    re.IGNORECASE,
)

# ── Capa 3: Futuro desde tercera persona (me van a pagar, el cliente pagará) ──
_CAPA_TERCERO = re.compile(
    r"\bme van a (?:pagar|depositar|transferir|cobrar|mandar|pasar|enviar)\b|"
    r"\bvan a (?:pagarme|cobrarme|depositarme|mandarme|transferirme)\b|"
    r"\bme (?:pagarán|depositarán|transferirán|cobrarán|mandarán|llegarán|pasarán)\b|"
    r"\bme (?:pagará[n]?|depositará[n]?|transferirá[n]?|cobrará[n]?)\b|"
    r"\b(?:el |mi )?cliente (?:va a pagar|pagará|me va a pagar|me pagará|piensa pagar)\b|"
    r"\b(?:el |mi )?(?:jefe|empresa|empleador).{0,20}(?:va a pagar|pagará|me pagará)\b|"
    r"\b(?:pap[aá]|mam[aá]|padres?|familia).{0,35}(?:va[n]? a (?:mandar|pasar|depositar|transferir|enviar))\b|"
    r"\bme (?:van a caer|están por llegar|está[n]? por depositar)\b|"
    r"\bme (?:está[n]? (?:debiendo|quedando debiendo)|siguen debiendo|quedan debiendo)\b",
    re.IGNORECASE,
)

# ── Capa 4: Marcadores temporales futuros explícitos ──
_CAPA_TIEMPO = re.compile(
    r"\bmañana\b|\bpasado mañana\b|"
    r"\besta (?:semana|quincena|tarde|noche)\b(?=.{0,60}(?:\d|pagar|cobrar|k\b|pesos|usd))|"
    r"\beste (?:mes|año|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b|"
    r"\bel (?:pr[oó]ximo|siguiente)\b|\bla (?:pr[oó]xima|siguiente)\b|"
    r"\bpr[oó]ximo[as]?\b|\bsiguiente[s]?\b(?=.{0,40}(?:pago|cobro|mes|semana|cuota|ingreso|egreso|quincena))|"
    r"\ben \d+ (?:d[ií]as?|semanas?|meses?|horas?)\b|"
    r"\bpara (?:el|la|fin de|final de) (?:mes|semana|quincena|\d)|"
    r"\bantes de (?:fin de mes|la quincena|que |el \d)|"
    r"\ba (?:fin|final) de mes\b|"
    r"\bla semana que viene\b|\bel mes que viene\b|"
    r"\bpara (?:el viernes|el lunes|el martes|el mi[eé]rcoles|el jueves|el s[aá]bado|el domingo)\b",
    re.IGNORECASE,
)

# ── Capa 5: Pendientes y cuentas sin saldar (estáticos, sin verbo de futuro) ──
_CAPA_PENDIENTE = re.compile(
    r"\bpendiente[s]?\b(?=.{0,60}(?:\d|k\b|pesos|usd|cobro|pago|factura|lucas))|"
    r"\bpor (?:pagar|cobrar|facturar|recibir|confirmar|saldar|liquidar)\b|"
    r"\bme deben\b|\bdeben pagarme\b|\btengo que cobrar\b|"
    r"\bfactura[s]? por cobrar\b|\bcuenta[s]? por cobrar\b|\bcuenta[s]? por pagar\b|"
    r"\bsaldo por pagar\b|\bsaldo pendiente\b|\bdeuda pendiente\b|"
    r"\bcobro pendiente\b|\bpago pendiente\b|\bfactura pendiente\b|"
    r"\baún no (?:ha llegado|ha entrado|han pagado)\b",
    re.IGNORECASE,
)

# ── Capa 6: Negación de hecho pasado = pendiente futuro ──
_CAPA_NEGACION = re.compile(
    r"\b(?:aún|todav[ií]a)\b.{0,20}(?:no\b.{0,15})?(?:he |haber )?(?:pagado|cobrado|recibido|facturado|transferido|llegado)\b|"
    r"\bno (?:he|lo he|la he|los he|las he) (?:pagado|cobrado|recibido|facturado|transferido)\b|"
    r"\bsin (?:haber )?(?:pagar|cobrar|saldar|liquidar|facturar)\b|"
    r"\bfalta(?:n)? (?:por )?(?:pagar|cobrar)\b|"
    r"\bno ha(?:n)? (?:pagado|depositado|transferido|llegado|caído)\b|"
    r"\bno se ha (?:pagado|cobrado|depositado)\b",
    re.IGNORECASE,
)

# ── Capa 7: Condicionales financieros (si X → Y dinero) ──
_CAPA_CONDICIONAL = re.compile(
    r"\bsi (?:vendo|cobro|factur[oa]|recibo|llega|me pagan|consigo|cierro|firma[n]?|aprueba[n]?|entrega[n]?)\b|"
    r"\bcuando (?:llegue|reciba|paguen|me paguen|cobre|facture|venda|depositen|confirmen|entre el)\b|"
    r"\bapenas (?:llegue|reciba|paguen|me paguen|cobre|venda|confirmen|entre)\b|"
    r"\btan pronto (?:como )?(?:llegue|reciba|paguen|entre|cobren)\b|"
    r"\bde (?:llegar|cobrar|vender|facturar|recibir).{0,20}\bganar[ía]*\b",
    re.IGNORECASE,
)

# ── Capa 8: Recurrentes y fechas de vencimiento ──
_CAPA_RECURRENTE = re.compile(
    r"\b(?:pr[oó]xima?|proximo?|siguiente) (?:cuota|mensualidad|pago|cobro|factura|arriendo|alquiler|cargo|abono)\b|"
    r"\b(?:cuota|mensualidad|arriendo|alquiler|suscripci[oó]n).{0,30}(?:pr[oó]ximo|este mes|siguiente|en \d|mañana)\b|"
    r"\brenovaci[oó]n\b.{0,50}(?:pr[oó]xima?|este mes|en \d|vence|mañana)|"
    r"\bvence\b.{0,40}(?:el|en|pr[oó]ximo|esta semana|este mes|\d)|"
    r"\bvencimiento\b|\bfecha l[ií]mite\b|\bfecha de pago\b|\bfecha de cobro\b|"
    r"\bcargo (?:automático|recurrente|mensual|anual)\b|"
    r"\b(?:débito|debito) (?:automático|recurrente|programado)\b",
    re.IGNORECASE,
)

# Mapa nombre → patrón (en orden de peso descendente)
_CAPAS_PROYECCION: list[tuple[str, re.Pattern]] = [
    ("modal",       _CAPA_MODAL),
    ("espera",      _CAPA_ESPERA),
    ("tercero",     _CAPA_TERCERO),
    ("tiempo",      _CAPA_TIEMPO),
    ("pendiente",   _CAPA_PENDIENTE),
    ("negacion",    _CAPA_NEGACION),
    ("condicional", _CAPA_CONDICIONAL),
    ("recurrente",  _CAPA_RECURRENTE),
]

# ── Scorer de dirección INGRESO ──────────────────────────────────────────────
_DIR_INGRESO = re.compile(
    r"\bcobrar\b|\bcobro\b|\bcobr[eé]\b|"
    r"\bfacturar\b|\bfactur[eé]\b|"
    r"\brecibir\b|\brecib[ií]\b|"
    r"\bvender\b|\bvend[ií]\b|\bventa[s]?\b|"
    r"\bganar\b|\bgano\b|\bgan[eé]\b|"
    r"\bingreso[s]?\b|\bingresar\b|"
    r"\bme van a (?:pagar|mandar|depositar|pasar|enviar)\b|"
    r"\bme (?:pagarán|mandará[n]?|depositarán|pasarán)\b|"
    r"\bme deben\b|\bdeben pagarme\b|"
    r"\bcliente.{0,20}(?:pag|cobr)\b|"
    r"\bbono\b|\bcomisi[oó]n\b|\bhonorario[s]?\b|\bdividendo[s]?\b|"
    r"\butilidad\b|\bretorno\b|\brenta\b|"
    r"\bfreelance\b|\bconsultor[ií]a\b|\bservicio[s]?\b|\bproyecto\b|"
    r"\bproducto digital\b|\bplantilla\b|\btemplate\b|\btienda\b|\becommerce\b|"
    r"\bcurso\b|\bebook\b|\bmentor[ií]a\b",
    re.IGNORECASE,
)

# ── Scorer de dirección EGRESO ───────────────────────────────────────────────
_DIR_EGRESO = re.compile(
    r"\bpagar\b|\bpago\b|\bpagu[eé]\b|"
    r"\bcomprar\b|\bcompr[eé]\b|"
    r"\bgastar\b|\bgast[eé]\b|"
    r"\begreso[s]?\b|\bcosto[s]?\b|\bgasto[s]?\b|"
    r"\barriendo\b|\balquiler\b|\bhipoteca\b|"
    r"\bservicio[s]? (?:público[s]?|de)\b|\binternet\b|\bcelular\b|"
    r"\bagua\b|\bluz\b|\bgas\b|\belectricidad\b|"
    r"\bdeuda[s]?\b|\bpr[eé]stamo\b|\bcr[eé]dito\b|\btarjeta\b|"
    r"\bsuscripci[oó]n\b|\brenovaci[oó]n\b|\bcuota[s]?\b|\bmensualidad\b|"
    r"\bmulta\b|\bimpuesto[s]?\b|\bseguro\b|\bp[oó]liza\b|"
    r"\bmatr[ií]cula\b|\barancel\b|\bcargo\b|"
    r"\bme van a cobrar\b|\bme cobrará[n]?\b",
    re.IGNORECASE,
)

# ── Categorías para proyecciones ─────────────────────────────────────────────
_CATS_PROYECCION: list[tuple[str, str]] = [
    ("freelance",       r"\bfreelance\b|\bcobrar\b|\bfacturar\b|\bconsultor[ií]a\b|\bservicio[s]?\b|\bproyecto\b|\bcliente\b|\bhonorario\b|\bcontrato\b|\bdesarroll[oa]\b|\bdise[ñn]o\b|\bmentor[ií]a\b"),
    ("ventas_digitales",r"\bventa digital\b|\bvender\b|\bplantilla\b|\btemplate\b|\bproducto digital\b|\btienda\b|\becommerce\b|\bcurso\b|\bebook\b"),
    ("mesada",          r"\bpap[aá]\b|\bmam[aá]\b|\bpadres?\b|\bfamilia\b|\bmesada\b"),
    ("arriendo",        r"\barriendo\b|\balquiler\b|\bhipoteca\b|\brenta del\b"),
    ("servicios_fijos", r"\binternet\b|\bcelular\b|\bagua\b|\bluz\b|\bgas\b|\belectricidad\b|\bservicio[s]? público[s]?\b"),
    ("deuda",           r"\bdeuda\b|\bpr[eé]stamo\b|\bcr[eé]dito\b|\bcuota\b|\bmensualidad\b|\babono\b|\bcuotas\b"),
    ("suscripcion",     r"\bsuscripci[oó]n\b|\brenovaci[oó]n\b|\bmembres[ií]a\b|\bcargo (?:automático|mensual|anual)\b"),
    ("tc_pago",         r"\btarjeta\b|\btc\b|\bcr[eé]dito\b"),
    ("ibkr",            r"\bibkr\b|\betf\b|\bacciones\b|\binversi[oó]n\b|\bmercado de valores\b"),
    ("nu",              r"\bnu\b|\bcajita\b|\bnubank\b"),
]


def _detectar_proyeccion(texto: str) -> tuple[bool, str, str, str]:
    """
    Análisis multi-señal para determinar si el texto describe un movimiento
    financiero futuro o pendiente (no ejecutado aún).

    Returns:
        (es_proyeccion, direccion, categoria, confianza)
        - direccion : 'ingreso' | 'egreso'
        - categoria : string
        - confianza : 'alta' | 'media'
    """
    t = texto.lower()

    # ── Evaluar cada capa ────────────────────────────────────────────────────
    capas_activas = [nombre for nombre, patron in _CAPAS_PROYECCION if patron.search(t)]

    if not capas_activas:
        return False, "egreso", "otro", "alta"

    # Confianza: ≥2 capas o cualquier capa de alta densidad semántica
    capas_alta_densidad = {"modal", "pendiente", "negacion", "tercero"}
    if len(capas_activas) >= 2 or capas_activas[0] in capas_alta_densidad:
        confianza = "alta"
    else:
        confianza = "media"

    # ── Scoring de dirección ─────────────────────────────────────────────────
    score_ing = len(_DIR_INGRESO.findall(t))
    score_egr = len(_DIR_EGRESO.findall(t))

    if score_ing > score_egr:
        direccion = "ingreso"
    elif score_egr > score_ing:
        direccion = "egreso"
    else:
        # Tie: desempate semántico
        tiene_verbo_pago = bool(re.search(r"\bpagar\b|\bpago\b|\bdeuda\b|\barriendo\b|\bsuscripci[oó]n\b", t, re.IGNORECASE))
        direccion = "egreso" if tiene_verbo_pago else "ingreso"

    # ── Categoría ────────────────────────────────────────────────────────────
    categoria = "otro"
    for cat, patron in _CATS_PROYECCION:
        if re.search(patron, t, re.IGNORECASE):
            categoria = cat
            break

    return True, direccion, categoria, confianza


def _mensaje_proyeccion(
    direccion: str, categoria: str,
    moneda: str, monto_original: float, monto_cop: int
) -> str:
    """Genera retroalimentación contextual según la proyección detectada."""
    if moneda == "USD":
        ms = f"${monto_original:g} USD (~${monto_cop:,} COP)"
    else:
        ms = f"${monto_cop:,} COP"

    if direccion == "ingreso":
        base = {
            "freelance":        f"Cobro de servicios proyectado ({ms}). Actualiza cuando el cliente confirme.",
            "ventas_digitales": f"Venta digital proyectada ({ms}). Confírmala cuando el dinero entre.",
            "mesada":           f"Ingreso familiar esperado ({ms}). Anótalo como real cuando llegue.",
            "ibkr":             f"Retorno de inversión proyectado ({ms}) anotado.",
            "nu":               f"Ingreso esperado a cajitas Nu ({ms}).",
            "otro":             f"Ingreso proyectado de {ms} registrado. Confírmalo cuando sea real.",
        }
    else:
        base = {
            "arriendo":         f"Pago de arriendo pendiente ({ms}) registrado. Tenlo en tu flujo de caja.",
            "servicios_fijos":  f"Pago de servicios fijos proyectado ({ms}). Cuéntalo en tu caja disponible.",
            "deuda":            f"Cuota o pago de deuda proyectado ({ms}). Revisa tu disponible antes.",
            "suscripcion":      f"Renovación/suscripción proyectada ({ms}) anotada.",
            "tc_pago":          f"Pago de tarjeta proyectado ({ms}). Asegúrate de tener el saldo listo.",
            "otro":             f"Egreso proyectado de {ms} registrado en tu flujo de caja.",
        }

    return base.get(categoria, base["otro"])


# ══════════════════════════════════════════════════════════════════════════════
#  REGLAS DE TRANSACCIONES REALES (no proyecciones)
# ══════════════════════════════════════════════════════════════════════════════

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
        "nombre": "ingreso_mesada",
        "pattern": r"pap[aá]|mam[aá]|\bpapa\b|\bmama\b|padres|familia|mesada",
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
        "nombre": "ingreso_general",
        "pattern": r"recib[ií]|me lleg[oó]|me ca[iy][oó]|entr[oó]|me mandaron|me mand[oó]|me pasaron|me pas[oó]|me depositaron|me deposit[oó]|me transfirieron|me dieron|me dio\b",
        "tipo": "ingreso",
        "categoria": "otro",
        "mensaje": "Ingreso registrado. Cuéntame más si quieres una categoría específica.",
    },
    {
        "nombre": "egreso_tarjeta",
        "pattern": r"tarjeta|\btc\b|cr[eé]dito|pago de tarjeta",
        "tipo": "egreso",
        "categoria": "tc_pago",
        "mensaje": "Pago de tarjeta registrado. Bien hecho pagarlo completo.",
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


# ══════════════════════════════════════════════════════════════════════════════
#  EXTRACTOR DE MONTO
# ══════════════════════════════════════════════════════════════════════════════

def _extraer_monto(texto: str) -> tuple[float, str]:
    """
    Extrae monto y moneda del texto.
    Retorna (monto, moneda). monto=0 si no se encuentra.
    """
    t = texto.lower().replace(",", ".")

    # 1. USD con sufijo: 25 usd, 25 dólares
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:usd|d[oó]lares?|dolares?|d[oó]lar)", t)
    if m:
        return float(m.group(1)), "USD"

    # 2. USD con prefijo $: $25 usd
    m = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:usd|dolares?|d[oó]lares?)", t)
    if m:
        return float(m.group(1)), "USD"

    # 3. COP millones — incluye "palos" y acento en millón
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mill[oó]n(?:es)?|millon(?:es)?|palos?)", t)
    if m:
        return float(m.group(1)) * 1_000_000, "COP"

    # 4. COP miles: 900k, 40 mil, 5 lucas, 3 lks
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:k|mil|lucas?|lks?)\b", t)
    if m:
        return float(m.group(1)) * 1_000, "COP"

    # 5. COP formato colombiano con $: $900.000
    m = re.search(r"\$\s*(\d{1,3}(?:\.\d{3})+)", t)
    if m:
        return float(m.group(1).replace(".", "")), "COP"

    # 6. COP plano con separador de miles: 900.000 pesos
    m = re.search(r"(\d{1,3}(?:\.\d{3})+)\s*(?:pesos?|cop)?", t)
    if m:
        return float(m.group(1).replace(".", "")), "COP"

    # 7. COP número largo sin sufijo — excluye años (1900-2099)
    m = re.search(r"\b(\d{4,})\b", t)
    if m:
        val = float(m.group(1))
        if not (1900 <= val <= 2099):
            return val, "COP"

    # 8. Número corto sin sufijo — último recurso (50, 100, 3.5)
    m = re.search(r"\b(\d{1,3}(?:\.\d+)?)\b", t)
    if m:
        val = float(m.group(1))
        if val > 0:
            return val, "COP"

    return 0, "COP"


# ══════════════════════════════════════════════════════════════════════════════
#  CLASIFICADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def clasificar(texto: str, moneda_forzada: Optional[str] = None) -> ResultadoClasificacion:
    """
    Clasifica un texto libre en un movimiento financiero.

    Pipeline:
        1. Preprocesamiento
        2. Extracción de monto
        3. Motor de proyecciones (8 capas de señales)
        4. Reglas de transacciones reales
        5. Fallback

    Args:
        texto: Texto en lenguaje natural.
        moneda_forzada: 'USD' | 'COP'. Si es 'USD' y el texto no especifica
                        explícitamente la moneda, el monto se trata como USD.
    """
    texto_limpio = texto.strip()
    if not texto_limpio:
        return ResultadoClasificacion(
            error="Escribe un poco más. Ejemplo: 'gasté 45k en almuerzo' o 'mis papás me pasaron 800k'."
        )

    monto, moneda = _extraer_monto(texto_limpio)

    # Aplicar moneda forzada — el texto explícito siempre gana
    if moneda_forzada == "USD" and moneda == "COP":
        t_chk = texto_limpio.lower()
        tiene_usd = bool(re.search(r"\b(?:usd|d[oó]lares?|dolares?)\b", t_chk))
        tiene_cop = bool(re.search(r"\b(?:pesos?|cop)\b", t_chk))
        if not tiene_usd and not tiene_cop:
            moneda = "USD"

    monto_cop = round(monto * TASA_COP_USD) if moneda == "USD" and monto > 0 else round(monto)

    # ── Paso 1: Motor de proyecciones ────────────────────────────────────────
    es_proy, direccion, categoria_proy, confianza_proy = _detectar_proyeccion(texto_limpio)

    if es_proy:
        if monto <= 0:
            return ResultadoClasificacion(
                error="Detecté que es una proyección pero no encontré el monto. "
                      "Ejemplo: 'voy a pagar 800k de arriendo' o 'espero cobrar $50 USD del cliente'."
            )
        return ResultadoClasificacion(
            tipo=f"proyeccion_{direccion}",
            categoria=categoria_proy,
            descripcion=texto_limpio,
            monto_cop=monto_cop,
            monto_original=monto,
            moneda=moneda,
            es_proyeccion=True,
            mensaje_respuesta=_mensaje_proyeccion(direccion, categoria_proy, moneda, monto, monto_cop),
            confianza=confianza_proy,
        )

    # ── Paso 2: Transacciones reales ─────────────────────────────────────────
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
                es_proyeccion=False,
                mensaje_respuesta=regla["mensaje"],
                confianza="alta",
            )

    # ── Fallback con monto ────────────────────────────────────────────────────
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

    return ResultadoClasificacion(
        error="Escribe un poco más. Ejemplo: 'gasté 45k en almuerzo' o 'mis papás me pasaron 800k'."
    )
