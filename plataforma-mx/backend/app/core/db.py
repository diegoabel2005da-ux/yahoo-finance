"""Persistencia. PostgreSQL en producción (DATABASE_URL), SQLite en desarrollo/pruebas."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Integer, MetaData, Numeric, String, Text,
    UniqueConstraint, create_engine, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./plataforma.db")
# Esquema de PostgreSQL para las tablas de la plataforma. En Supabase conviene uno distinto de «public»,
# que se publica automáticamente por la API REST del proyecto. En SQLite no aplica.
DB_SCHEMA = os.environ.get("DB_SCHEMA") or (None if DATABASE_URL.startswith("sqlite") else "plataforma")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(schema=DB_SCHEMA)


class Instrument(Base):
    """Emisora + serie. Una emisora con varias series genera varios registros."""

    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("ticker", "series", name="uq_ticker_series"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    issuer_name: Mapped[str] = mapped_column(String(200))
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    series: Mapped[str] = mapped_column(String(10))
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    yahoo_symbol: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    exchange: Mapped[str] = mapped_column(String(10))  # BMV / BIVA
    currency: Mapped[str] = mapped_column(String(3), default="MXN")
    derivatives: Mapped[list] = mapped_column(JSON, default=list)  # ["futuro", "opcion"]
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    catalog_source: Mapped[str] = mapped_column(String(500))
    reviewed_on: Mapped[date] = mapped_column(Date)
    catalog_revision_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_revisions.id"), nullable=True)


class CatalogRevision(Base):
    __tablename__ = "catalog_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(500))
    file_sha256: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    rows_accepted: Mapped[int] = mapped_column(Integer)
    rows_rejected: Mapped[int] = mapped_column(Integer)
    report: Mapped[dict] = mapped_column(JSON)


class PriceRecord(Base):
    __tablename__ = "price_records"
    __table_args__ = (
        UniqueConstraint("instrument_id", "market_date", "price_type", "field", "source", "data_version",
                         name="uq_price_obs"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    field: Mapped[str] = mapped_column(String(16))  # open/high/low/close/volume/value
    price_type: Mapped[str] = mapped_column(String(40))
    market_date: Mapped[date] = mapped_column(Date, index=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quote_time: Mapped[str | None] = mapped_column(String(12), nullable=True)
    timezone: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3))
    value_raw: Mapped[str] = mapped_column(String(40))
    value: Mapped[float] = mapped_column(Numeric(24, 10))
    precision: Mapped[int] = mapped_column(Integer)
    market: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(500))
    origin: Mapped[str] = mapped_column(String(40))
    freshness: Mapped[str] = mapped_column(String(30))
    validation: Mapped[str] = mapped_column(String(20))
    data_version: Mapped[str] = mapped_column(String(20))
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)

    instrument = relationship("Instrument")


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(300))
    file_sha256: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(500))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    report: Mapped[dict] = mapped_column(JSON)


class Discrepancy(Base):
    __tablename__ = "discrepancies"
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    market_date: Mapped[date] = mapped_column(Date)
    price_type: Mapped[str] = mapped_column(String(40))
    field: Mapped[str] = mapped_column(String(16))
    reference_source: Mapped[str] = mapped_column(String(500))
    reference_value: Mapped[str] = mapped_column(String(40))
    candidate_source: Mapped[str] = mapped_column(String(500))
    candidate_value: Mapped[str] = mapped_column(String(40))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class RateObservation(Base):
    __tablename__ = "rate_observations"
    __table_args__ = (UniqueConstraint("rate_code", "market_date", "source", name="uq_rate_obs"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rate_code: Mapped[str] = mapped_column(String(40), index=True)  # p.ej. TIIE_FONDEO, TIIE_28
    rate_name: Mapped[str] = mapped_column(String(200))
    tenor: Mapped[str] = mapped_column(String(20))
    market_date: Mapped[date] = mapped_column(Date, index=True)
    value_raw: Mapped[str] = mapped_column(String(40))  # en porcentaje, tal como se publica
    convention: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(500))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    origin: Mapped[str] = mapped_column(String(40))
    validation: Mapped[str] = mapped_column(String(20))


class CurveSnapshot(Base):
    __tablename__ = "curve_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    curve_date: Mapped[date] = mapped_column(Date)
    quote_kind: Mapped[str] = mapped_column(String(30))  # zero_rate / discount_factor
    compounding: Mapped[str] = mapped_column(String(30))
    day_count: Mapped[str] = mapped_column(String(20))
    interpolation: Mapped[str] = mapped_column(String(30))
    points: Mapped[list] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(500))
    origin: Mapped[str] = mapped_column(String(40))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FinancialStatement(Base):
    __tablename__ = "financial_statements"
    __table_args__ = (UniqueConstraint("ticker", "period_end", "period_type", "statement",
                                       "basis", "source", name="uq_fin_stmt"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    statement: Mapped[str] = mapped_column(String(20))  # income / balance / cashflow
    period_type: Mapped[str] = mapped_column(String(10))  # Q / FY
    period_end: Mapped[date] = mapped_column(Date)
    basis: Mapped[str] = mapped_column(String(20))  # consolidado / individual
    currency: Mapped[str] = mapped_column(String(3))
    units: Mapped[str] = mapped_column(String(20))  # pesos, miles, millones
    items: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(500))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FuturesContract(Base):
    __tablename__ = "futures_contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), unique=True)
    underlying_ticker: Mapped[str] = mapped_column(String(20), index=True)
    expiry: Mapped[date] = mapped_column(Date)
    multiplier: Mapped[float] = mapped_column(Numeric(18, 6))
    tick_size: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    tick_value: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    last_settlement: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    previous_settlement: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    open_interest: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    settlement: Mapped[str] = mapped_column(String(20))  # fisica / financiera
    initial_margin: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)  # AIM (máx. larga/corta)
    margin_long: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    margin_short: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    margin_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    margin_source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(500))
    reviewed_on: Mapped[date] = mapped_column(Date)


class OptionContract(Base):
    __tablename__ = "option_contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(60), unique=True)
    underlying_ticker: Mapped[str] = mapped_column(String(20), index=True)
    option_type: Mapped[str] = mapped_column(String(4))  # call / put
    strike: Mapped[float] = mapped_column(Numeric(18, 6))
    expiry: Mapped[date] = mapped_column(Date)
    multiplier: Mapped[float] = mapped_column(Numeric(18, 6))
    style: Mapped[str] = mapped_column(String(10))  # europea / americana
    settlement: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    underlying_series: Mapped[str | None] = mapped_column(String(10), nullable=True)
    strike_published: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    strike_scale: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)  # None = escala no verificada
    margin_long: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    margin_short: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    margin_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    margin_source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_settlement: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    previous_settlement: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    open_interest: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(500))
    reviewed_on: Mapped[date] = mapped_column(Date)


class CorporateAction(Base):
    """Dividendos y splits por emisora y serie, con su fuente."""

    __tablename__ = "corporate_actions"
    __table_args__ = (UniqueConstraint("ticker", "series", "kind", "ex_date", "source_key", name="uq_corp_action"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    series: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(10))  # dividendo / split
    ex_date: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[float] = mapped_column(Numeric(24, 8))  # monto por acción, o razón del split (p. ej. 2.0 = 2 por 1)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    source: Mapped[str] = mapped_column(String(500))
    source_key: Mapped[str] = mapped_column(String(60))
    origin: Mapped[str] = mapped_column(String(40), default="observado_fuente_oficial")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContractQuote(Base):
    """Historial de precios de liquidación oficiales por contrato listado (boletines de MexDer)."""

    __tablename__ = "contract_quotes"
    __table_args__ = (UniqueConstraint("contract_kind", "symbol", "market_date", "source", name="uq_contract_quote"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_kind: Mapped[str] = mapped_column(String(10))  # futuro / opcion
    symbol: Mapped[str] = mapped_column(String(60), index=True)
    market_date: Mapped[date] = mapped_column(Date, index=True)
    price_type: Mapped[str] = mapped_column(String(40), default="precio_liquidacion")
    previous_settlement: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    settlement: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    open_interest: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="MXN")
    source: Mapped[str] = mapped_column(String(500))
    origin: Mapped[str] = mapped_column(String(40), default="observado_fuente_oficial")
    file_sha256: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Exposure(Base):
    __tablename__ = "exposures"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # equity / rate_liability / rate_asset
    declared: Mapped[bool] = mapped_column(Boolean)  # real declarada vs hipotética
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Study(Base):
    __tablename__ = "studies"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))
    version: Mapped[int] = mapped_column(Integer, default=1)
    inputs: Mapped[dict] = mapped_column(JSON)
    results: Mapped[dict] = mapped_column(JSON)
    audit_id: Mapped[int | None] = mapped_column(ForeignKey("audit_records.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditRecord(Base):
    __tablename__ = "audit_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    calculation: Mapped[str] = mapped_column(String(100), index=True)
    engine_version: Mapped[str] = mapped_column(String(20))
    inputs: Mapped[dict] = mapped_column(JSON)
    parameters: Mapped[dict] = mapped_column(JSON)
    formulas: Mapped[list] = mapped_column(JSON)
    data_sources: Mapped[list] = mapped_column(JSON)
    transformations: Mapped[list] = mapped_column(JSON)
    result_digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_engine = None
SessionLocal = None


def init_db(url: str | None = None):
    global _engine, SessionLocal
    url = url or DATABASE_URL
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if url == "sqlite://":
        from sqlalchemy.pool import StaticPool
        kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, future=True, **kwargs)
    if url.startswith("sqlite"):
        # SQLite no tiene esquemas: las tablas se crean sin prefijo.
        _engine = _engine.execution_options(schema_translate_map={DB_SCHEMA: None} if DB_SCHEMA else None)
    elif DB_SCHEMA:
        with _engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"'))
    Base.metadata.create_all(_engine)
    SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_session():
    if SessionLocal is None:
        init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
