"""Registro histórico en SQLite: archivos, liquidaciones, facturas, arqueos y hallazgos."""
import sqlite3
from datetime import date, datetime
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS archivos (
    id INTEGER PRIMARY KEY, nombre TEXT, hash TEXT UNIQUE, tipo TEXT,
    fecha_proceso TEXT, estado TEXT, revision TEXT
);
CREATE TABLE IF NOT EXISTS liquidaciones (
    id INTEGER PRIMARY KEY, archivo_id INTEGER, caja TEXT, custodio TEXT, cedula_custodio TEXT,
    numero TEXT, fecha TEXT, monto_solicitado REAL, total_facturas REAL, n_facturas INTEGER,
    n_rechazadas INTEGER, n_observadas INTEGER, estado TEXT, fecha_proceso TEXT, tipo_tramite TEXT
);
CREATE TABLE IF NOT EXISTS facturas (
    id INTEGER PRIMARY KEY, liquidacion_id INTEGER, archivo_id INTEGER, caja TEXT, fila INTEGER,
    fecha TEXT, tipo_doc TEXT, clave TEXT, consecutivo TEXT, proveedor TEXT, cedula_proveedor TEXT,
    receptor TEXT, cedula_receptor TEXT, descripcion TEXT, categoria TEXT, subtotal REAL, iva REAL,
    total REAL, moneda TEXT, total_crc REAL, solicitado_por TEXT, autorizado_por TEXT,
    estado TEXT, observaciones TEXT
);
CREATE INDEX IF NOT EXISTS ix_fact_clave ON facturas(clave);
CREATE INDEX IF NOT EXISTS ix_fact_prov ON facturas(cedula_proveedor, consecutivo);
CREATE TABLE IF NOT EXISTS arqueos (
    id INTEGER PRIMARY KEY, archivo_id INTEGER, caja TEXT, custodio TEXT, fecha TEXT,
    realizado_por TEXT, fondo REAL, efectivo REAL, pendientes_facturas REAL, vales REAL,
    diferencia REAL, estado TEXT, fecha_proceso TEXT
);
CREATE TABLE IF NOT EXISTS arqueo_pendientes (
    id INTEGER PRIMARY KEY, arqueo_id INTEGER, tipo TEXT, fecha TEXT, clave TEXT, numero TEXT,
    beneficiario TEXT, descripcion TEXT, monto REAL
);
CREATE TABLE IF NOT EXISTS comprobantes (
    clave TEXT PRIMARY KEY, tipo_doc TEXT, consecutivo TEXT, fecha TEXT, emisor_cedula TEXT, emisor_nombre TEXT,
    receptor_cedula TEXT, receptor_nombre TEXT, moneda TEXT, total REAL, impuesto REAL, descripcion TEXT,
    estado_hacienda TEXT, archivos TEXT, controles TEXT, estado TEXT, fecha_recepcion TEXT, fecha_actualizacion TEXT
);
CREATE TABLE IF NOT EXISTS verificaciones (
    id INTEGER PRIMARY KEY, archivo_id INTEGER, liquidacion_id INTEGER, arqueo_id INTEGER, caja TEXT,
    orden INTEGER, grupo TEXT, control TEXT, articulo TEXT, estado TEXT, detalle TEXT
);
CREATE TABLE IF NOT EXISTS respaldos (
    ruta TEXT, hash TEXT, drive_id TEXT, carpeta TEXT, nombre TEXT, fecha TEXT, PRIMARY KEY (ruta, hash)
);
CREATE TABLE IF NOT EXISTS portal_importados (
    envio TEXT PRIMARY KEY, persona TEXT, clave TEXT, importado TEXT
);
CREATE TABLE IF NOT EXISTS hallazgos (
    id INTEGER PRIMARY KEY, archivo_id INTEGER, origen TEXT, liquidacion_id INTEGER,
    arqueo_id INTEGER, factura_id INTEGER, factura_relacionada_id INTEGER, caja TEXT,
    severidad TEXT, regla TEXT, detalle TEXT, monto REAL, fecha_registro TEXT, gravedad TEXT, articulo TEXT,
    estado TEXT DEFAULT 'Abierto', comentario TEXT
);
"""


def _valor(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


class BaseDatos:
    def __init__(self, ruta: Path):
        self.con = sqlite3.connect(ruta)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        self._migrar()

    def _migrar(self):
        """Agrega columnas nuevas a bases creadas con versiones anteriores."""
        nuevas = {"hallazgos": {"gravedad": "TEXT", "articulo": "TEXT"}, "liquidaciones": {"tipo_tramite": "TEXT"}}
        for tabla, columnas in nuevas.items():
            existentes = {r[1] for r in self.con.execute(f"PRAGMA table_info({tabla})")}
            for col, tipo in columnas.items():
                if col not in existentes:
                    self.con.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")

    def insertar(self, tabla: str, datos: dict) -> int:
        columnas = list(datos)
        cur = self.con.execute(
            f"INSERT INTO {tabla} ({','.join(columnas)}) VALUES ({','.join('?' * len(columnas))})",
            [_valor(datos[c]) for c in columnas],
        )
        return cur.lastrowid

    def actualizar(self, tabla: str, id_: int, datos: dict):
        asignaciones = ",".join(f"{c}=?" for c in datos)
        self.con.execute(f"UPDATE {tabla} SET {asignaciones} WHERE id=?",
                         [_valor(v) for v in datos.values()] + [id_])

    def consultar(self, sql: str, params=()) -> list[dict]:
        return [dict(r) for r in self.con.execute(sql, params).fetchall()]

    def archivo_procesado(self, hash_: str) -> dict | None:
        filas = self.consultar("SELECT * FROM archivos WHERE hash=?", (hash_,))
        return filas[0] if filas else None

    def liquidacion_existente(self, caja: str, numero: str) -> dict | None:
        filas = self.consultar("SELECT * FROM liquidaciones WHERE caja=? AND numero=?", (caja, numero))
        return filas[0] if filas else None

    def eliminar_liquidacion(self, liquidacion_id: int):
        """Una versión corregida reemplaza a la anterior (evita duplicados falsos)."""
        self.con.execute("DELETE FROM hallazgos WHERE liquidacion_id=?", (liquidacion_id,))
        self.con.execute("DELETE FROM verificaciones WHERE liquidacion_id=?", (liquidacion_id,))
        self.con.execute("UPDATE hallazgos SET factura_relacionada_id=NULL WHERE factura_relacionada_id IN "
                         "(SELECT id FROM facturas WHERE liquidacion_id=?)", (liquidacion_id,))
        self.con.execute("DELETE FROM facturas WHERE liquidacion_id=?", (liquidacion_id,))
        self.con.execute("DELETE FROM liquidaciones WHERE id=?", (liquidacion_id,))

    def facturas_historicas(self) -> list[dict]:
        return self.consultar(
            "SELECT f.*, l.numero AS liquidacion_numero, l.custodio FROM facturas f "
            "JOIN liquidaciones l ON l.id = f.liquidacion_id")

    def commit(self):
        self.con.commit()

    def cerrar(self):
        self.con.commit()
        self.con.close()
