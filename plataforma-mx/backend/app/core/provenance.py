"""Modelo de procedencia de datos.

Toda cifra de mercado que entra al sistema debe llevar su procedencia completa.
Este módulo define los tipos de precio, estados de actualización y validación, y
el registro de observación con todos los campos exigidos por la sección 3.1.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class PriceType(str, Enum):
    """Tipos de precio que NUNCA deben confundirse entre sí."""

    SPOT = "spot"
    LAST_TRADE = "ultimo_negociado"
    OFFICIAL_CLOSE = "cierre_oficial"
    ADJUSTED_CLOSE = "cierre_ajustado"
    PLACEMENT = "precio_colocacion"
    FUTURE = "precio_futuro"
    SETTLEMENT = "precio_liquidacion"
    OPTION_PREMIUM_OBSERVED = "prima_observada"
    THEORETICAL = "precio_teorico_calculado"


class Freshness(str, Enum):
    REALTIME = "tiempo_real"
    DELAYED = "retrasado"
    INTRADAY = "intradia"
    PRELIMINARY = "preliminar"
    OFFICIAL_CLOSE = "oficial_cierre"
    HISTORICAL = "historico"
    STALE = "desactualizado"
    UNAVAILABLE = "no_disponible"


class ValidationStatus(str, Enum):
    PENDING = "pendiente"
    VALIDATED = "validado"            # coincide con la referencia oficial
    UNVERIFIED = "no_verificado"      # sin referencia oficial con la cual comparar
    DISCREPANCY = "discrepancia"      # difiere de la referencia: bloquea cálculos críticos
    REJECTED = "rechazado"


class DataOrigin(str, Enum):
    """Distingue información observada de información producida por el sistema."""

    OBSERVED_OFFICIAL = "observado_fuente_oficial"
    OBSERVED_SECONDARY = "observado_proveedor_secundario"
    USER_DECLARED = "declarado_por_usuario"
    USER_ASSUMPTION = "supuesto_del_usuario"
    MODEL_OUTPUT = "resultado_de_modelo"


# Tipos de precio que sólo pueden originarse en un modelo.
MODEL_ONLY_TYPES = {PriceType.THEORETICAL}


class Observation(BaseModel):
    """Una observación de mercado con procedencia completa (sección 3.1)."""

    instrument: str = Field(..., description="Instrumento (p. ej. emisora)")
    series: str = Field(..., description="Serie del valor, p. ej. 'A', 'B', '*', 'CPO'")
    identifier: str = Field(..., description="Identificador inequívoco (ISIN o clave de pizarra)")
    market: str = Field(..., description="BMV, BIVA, MexDer, Banxico…")
    source: str = Field(..., description="Fuente concreta: URL, archivo o conector")
    price_type: PriceType
    market_date: date
    publication_date: Optional[date] = None
    retrieved_at: datetime
    timezone: str = "America/Mexico_City"
    time: Optional[str] = Field(None, description="Hora de la cotización, HH:MM:SS")
    currency: str = "MXN"
    value_raw: str = Field(..., description="Valor tal como fue publicado (texto)")
    published_precision: int = Field(..., ge=0, le=10)
    freshness: Freshness
    origin: DataOrigin = DataOrigin.OBSERVED_SECONDARY
    validation: ValidationStatus = ValidationStatus.PENDING
    data_version: str = "1"

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("moneda debe ser código ISO 4217 de 3 letras")
        return v

    @field_validator("value_raw")
    @classmethod
    def _value(cls, v: str) -> str:
        v = v.strip()
        try:
            Decimal(v)
        except InvalidOperation as exc:
            raise ValueError(f"valor no numérico: {v!r}") from exc
        return v

    @model_validator(mode="after")
    def _consistency(self) -> "Observation":
        if self.price_type in MODEL_ONLY_TYPES and self.origin != DataOrigin.MODEL_OUTPUT:
            raise ValueError("un precio teórico sólo puede tener origen 'resultado_de_modelo'")
        if self.origin == DataOrigin.MODEL_OUTPUT and self.price_type not in MODEL_ONLY_TYPES:
            raise ValueError("un resultado de modelo no puede etiquetarse como precio observado")
        if self.origin == DataOrigin.OBSERVED_OFFICIAL and self.validation == ValidationStatus.REJECTED:
            raise ValueError("observación oficial rechazada: no debe almacenarse como válida")
        # La precisión declarada debe ser coherente con el texto publicado.
        dec = Decimal(self.value_raw)
        exp = -dec.as_tuple().exponent if dec.as_tuple().exponent < 0 else 0
        if exp > self.published_precision:
            raise ValueError(
                f"el valor {self.value_raw} tiene {exp} decimales, más que la precisión publicada "
                f"({self.published_precision})"
            )
        if self.publication_date and self.publication_date < self.market_date:
            raise ValueError("la fecha de publicación no puede ser anterior a la fecha de mercado")
        return self

    @property
    def value(self) -> Decimal:
        return Decimal(self.value_raw)

    @property
    def is_blocking(self) -> bool:
        return self.validation in (ValidationStatus.DISCREPANCY, ValidationStatus.REJECTED)


class Provenance(BaseModel):
    """Metadato compacto adjunto a cualquier métrica mostrada en la interfaz."""

    source: str
    period: str
    methodology: str
    origin: DataOrigin
    as_of: Optional[date] = None
    notes: list[str] = []
