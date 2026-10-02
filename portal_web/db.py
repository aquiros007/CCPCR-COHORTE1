"""Base de datos del portal (Postgres en Railway, SQLite en desarrollo)."""
import json
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, String, Table, Text,
                        create_engine, inspect, insert, select, text, update)

from .config import DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    from pathlib import Path
    Path(DATABASE_URL.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)

motor = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
meta = MetaData()

proveedores = Table(
    "proveedores", meta,
    Column("id", Integer, primary_key=True),
    Column("cedula", String(20), unique=True, nullable=False),
    Column("razon_social", String(200), nullable=False),
    Column("nombre_comercial", String(200), default=""),
    Column("correo", String(200), unique=True, nullable=False),
    Column("telefono", String(40), default=""),
    Column("password_hash", String(300), nullable=False),
    Column("estado", String(20), default="Pendiente"),          # Pendiente / Aprobado / Rechazado
    Column("comentario", Text, default=""),
    Column("creado", DateTime(timezone=True)),
    Column("revisado", DateTime(timezone=True)),
    Column("es_prueba", Boolean, default=False),               # proveedor de prueba del superadministrador
)

envios = Table(
    "envios", meta,
    Column("id", Integer, primary_key=True),
    Column("proveedor_id", Integer, ForeignKey("proveedores.id"), nullable=False),
    Column("clave", String(50), unique=True, nullable=False),
    Column("consecutivo", String(20)),
    Column("fecha_emision", String(10)),
    Column("emisor_cedula", String(20)),
    Column("emisor_nombre", String(200)),
    Column("receptor_cedula", String(20)),
    Column("total", Float),
    Column("impuesto", Float),
    Column("moneda", String(5)),
    Column("hacienda", String(30)),
    Column("descripcion", Text),
    Column("controles", JSON),
    Column("cruce", String(30)),                # resultado de la verificación automática
    Column("estado", String(20), default="RECIBIDO"),   # RECIBIDO / EN_REVISION / APROBADO / DEVUELTO / RECHAZADO
    Column("comentario", Text, default=""),
    Column("archivos", JSON),                   # {pdf|factura|respuesta: {id, nombre, carpeta}}
    Column("carpeta", Text),
    Column("creado", DateTime(timezone=True)),
    Column("actualizado", DateTime(timezone=True)),
)

bitacora = Table(
    "bitacora", meta,
    Column("id", Integer, primary_key=True),
    Column("ts", DateTime(timezone=True)),
    Column("actor", String(200)),
    Column("accion", String(60)),
    Column("detalle", Text),
    Column("ip", String(60)),
)


def ahora():
    return datetime.now(timezone.utc)


def iniciar():
    meta.create_all(motor)
    _migrar()


def _migrar():
    """Columnas agregadas después del primer despliegue (create_all no altera tablas existentes)."""
    nuevas = {"proveedores": {"es_prueba": "BOOLEAN DEFAULT FALSE"}}
    insp = inspect(motor)
    with motor.begin() as c:
        for tabla, columnas in nuevas.items():
            existentes = {col["name"] for col in insp.get_columns(tabla)}
            for nombre, tipo in columnas.items():
                if nombre not in existentes:
                    c.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}"))


def registrar(actor: str, accion: str, detalle: str = "", ip: str = ""):
    with motor.begin() as c:
        c.execute(insert(bitacora).values(ts=ahora(), actor=actor, accion=accion, detalle=detalle[:2000], ip=ip))


def uno(consulta) -> dict | None:
    with motor.connect() as c:
        fila = c.execute(consulta).mappings().first()
        return dict(fila) if fila else None


def todos(consulta) -> list[dict]:
    with motor.connect() as c:
        return [dict(f) for f in c.execute(consulta).mappings().all()]


def ejecutar(sentencia):
    with motor.begin() as c:
        return c.execute(sentencia)
