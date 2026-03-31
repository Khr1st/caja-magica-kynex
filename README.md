# Caja Mágica — KYNEX Ventures

> Tesorería personal conversacional de Kent Díaz.  
> Registro de ingresos y egresos con lenguaje natural → clasificación automática → Excel con identidad visual.

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.11+ · FastAPI · Uvicorn |
| Frontend | HTML + CSS + JS vanilla (single-file) |
| Persistencia | JSON local (`data/movimientos.json`) |
| Excel | openpyxl — paleta KYNEX |
| NLP | regex + heurísticas en Python puro |
| Deploy | Railway.app (Nixpacks) |
| Mobile | PWA instalable con Service Worker |

## Estructura

```
caja-magica/
├── main.py             # API FastAPI
├── clasificador.py     # Motor NLP
├── excel_export.py     # Generador Excel 4 hojas
├── data/               # Persistencia JSON
├── static/
│   ├── index.html      # Frontend completo
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
- `facturé 2 horas a $25 USD` → ingreso/consultoría (convierte a COP)
- `pasé 150k a IBKR` → ahorro/ibkr
- `voy a facturar 5 horas el próximo mes` → proyección

## Deploy en Railway

1. Conecta el repo de GitHub en [railway.app](https://railway.app)
2. Variables de entorno: `PORT` (auto), `TASA_COP_USD`, `CAJA_MINIMA_COP`
3. Deploy automático con cada push

## Licencia

Uso personal — Kent Díaz / KYNEX Ventures © 2025
