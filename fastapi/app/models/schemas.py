from typing import List
from pydantic import BaseModel, Field


class PropiedadInput(BaseModel):
    modelo: str
    ciudad: str
    tipo: str
    area_m2: float   = Field(gt=0, le=10000, description="Área en m²")
    alcobas: int     = Field(ge=0, le=20)
    banos: int       = Field(ge=0, le=20)
    lat: float       = Field(ge=-4.3, le=13.0, description="Latitud")
    lon: float       = Field(ge=-81.8, le=-66.8, description="Longitud")


class PrediccionResultado(BaseModel):
    precio_estimado: float
    modelo_usado: str


class ModeloInfo(BaseModel):
    nombre: str
    r2: float
    etapa: str


class OpcionesResponse(BaseModel):
    ciudad: List[str]
    tipo: List[str]
