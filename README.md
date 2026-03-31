# Caja Mágica

> Tu tesorería personal inteligente.  
> Registra ingresos y egresos con lenguaje natural → clasificación automática → Excel + visualización en tiempo real.

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.11+ · FastAPI · Uvicorn |
| Frontend | HTML + CSS + JS vanilla (single-file) |
| Gráficos | Chart.js (CDN) — barras, torta, radar |
| Persistencia | JSON local (`data/movimientos.json`) + auto-sync Excel |
| Excel | openpyxl — 4 hojas con estilo profesional |
| NLP | regex + heurísticas en Python puro |
| Deploy | Railway.app (Nixpacks) |
| Mobile | PWA instalable con Service Worker |

## Estructura

```
caja-magica/
├── main.py             # API FastAPI
├── clasificador.py     # Motor NLP
├── excel_export.py     # Generador Excel 4 hojas
├── data/               # Persistencia JSON + Excel auto-sync
├── static/
│   ├── index.html      # Frontend con dashboard + gráficos
│   ├── manifest.json   # PWA manifest
│   ├── sw.js           # Service Worker
│   └── icons/          # SVG icons
├── Procfile
├── railway.toml
└── requirements.txt
```

## Uso local

```bash
pip install -r requirements.txt
python main.py
# → http://localhost:8000
```

## Ejemplos de entrada

- `mis papás me pasaron 900k` → ingreso/mesada
- `gasté 40k en almuerzo y bus` → egreso/alimentación
- `facturé 2 horas a $25 USD` → ingreso/freelance (convierte a COP)
- `pasé 150k a IBKR` → ahorro/ibkr
- `voy a facturar 5 horas el próximo mes` → proyección

## Deploy en Railway

1. Conecta el repo de GitHub en [railway.app](https://railway.app)
2. Variables de entorno: `PORT` (auto), `TASA_COP_USD`, `CAJA_MINIMA_COP`
3. Deploy automático con cada push

## Licencia

MIT
