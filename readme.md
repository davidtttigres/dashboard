# TTT Facturación - Consolidation Tool

Este proyecto automatiza la consolidación de datos de facturación y deuda desde múltiples hojas de cálculo de Google Sheets (organizadas por año) en una única "Capa Dorada" (Gold Layer) para análisis en Looker Studio.

## Características

- **Consolidación Multianual**: Lee automáticamente las pestañas de años (ej. "2024", "2025") de Google Sheets.
- **Normalización de Datos**: Limpia formatos de moneda, fechas y maneja valores nulos.
- **Cálculo de Deuda**: Genera snapshots mensuales de la deuda de cada cliente (0-3 meses, 3-6 meses, >6 meses).
- **Exportación Automática**: Escribe los resultados procesados en una pestaña llamada `Consolidacion` en el mismo Google Sheet.
- **Automatización Diaria**: Ejecución programada vía GitHub Actions.

## Estructura del Proyecto

```
ttt_facturacion/
├── .github/workflows/   # Configuración de GitHub Actions
├── credentials/         # Credenciales locales (no subidas a git)
├── notebook/            # Jupyter Notebooks para análisis interactivo
├── scripts/             # Scripts Python para producción
├── requirements.txt     # Dependencias del proyecto
└── README.md            # Documentación
```

## Configuración Local

1.  **Requisitos**: Python 3.10+
2.  **Instalación**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Credenciales**:
    - Coloca tu archivo `credentials.json` de Google Cloud Service Account en la carpeta `credentials/`.

4.  **Ejecución Manual**:
    ```bash
    python3 scripts/consolidacion.py
    ```
    Los logs se guardarán en `consolidacion.log` y en la terminal.

## Automatización (GitHub Actions)

El proyecto cuenta con un workflow configurado en `.github/workflows/daily_consolidation.yml` que ejecuta el script todos los días a las **05:00 UTC**.

