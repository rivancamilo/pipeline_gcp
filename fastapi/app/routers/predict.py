import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ModeloInfo,
    OpcionesResponse,
    PrediccionResultado,
    PropiedadInput,
)
from app.services import bigquery_service, model_service

logger = logging.getLogger("predict_router")
router = APIRouter(prefix="/api", tags=["prediccion"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/modelos", response_model=list[ModeloInfo])
async def listar_modelos():
    """Devuelve los top-N modelos disponibles (nombre, R², etapa)."""
    try:
        modelos = model_service.get_available_models()
        if not modelos:
            raise HTTPException(status_code=503, detail="No hay modelos registrados en MLflow.")
        return [
            ModeloInfo(nombre=m["nombre"], r2=round(m["r2"], 4), etapa=m["etapa"])
            for m in modelos
        ]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error listando modelos: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudieron obtener los modelos.")


@router.get("/opciones", response_model=OpcionesResponse)
async def opciones():
    """Valores únicos de ciudad, tipo y estado para los selects del formulario."""
    try:
        return OpcionesResponse(
            ciudad=bigquery_service.get_distinct_values("ciudad"),
            tipo=bigquery_service.get_distinct_values("tipo"),
        )
    except Exception as exc:
        logger.error("Error cargando opciones: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudieron cargar las opciones del formulario.")


@router.post("/predict", response_model=PrediccionResultado)
async def predecir(entrada: PropiedadInput):
    """Ejecuta la predicción con el modelo seleccionado y devuelve el precio estimado."""
    try:
        precio = model_service.predict(entrada.modelo, entrada.model_dump())
        return PrediccionResultado(precio_estimado=precio, modelo_usado=entrada.modelo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Error en predicción: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al calcular la predicción. Intente de nuevo.")
