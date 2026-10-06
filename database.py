import sqlite3
from datetime import datetime

DB_NAME = "inventario.db"


def init_db():
    """Crea las tablas si no existen."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            cantidad INTEGER NOT NULL DEFAULT 0,
            precio REAL NOT NULL DEFAULT 0,
            categoria TEXT DEFAULT 'general',
            creado TEXT,
            actualizado TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER,
            tipo TEXT,
            cantidad INTEGER,
            fecha TEXT,
            FOREIGN KEY(producto_id) REFERENCES productos(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS conteos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            fecha_inicio TEXT,
            fecha_fin TEXT,
            estado TEXT DEFAULT 'abierto'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS conteo_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conteo_id INTEGER NOT NULL,
            producto_id INTEGER NOT NULL,
            cantidad_sistema INTEGER,
            cantidad_contada INTEGER,
            fecha TEXT,
            UNIQUE(conteo_id, producto_id),
            FOREIGN KEY(conteo_id) REFERENCES conteos(id),
            FOREIGN KEY(producto_id) REFERENCES productos(id)
        )
    """)
    conn.commit()
    conn.close()


def agregar_producto(nombre, cantidad, precio, categoria="general"):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    ahora = datetime.now().isoformat()
    try:
        c.execute("""INSERT INTO productos 
            (nombre, cantidad, precio, categoria, creado, actualizado)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (nombre.lower(), cantidad, precio, categoria, ahora, ahora))
        conn.commit()
        return True, "Producto agregado correctamente."
    except sqlite3.IntegrityError:
        return False, "El producto ya existe."
    finally:
        conn.close()


def actualizar_stock(nombre, cantidad, tipo="entrada"):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, cantidad FROM productos WHERE nombre = ?", (nombre.lower(),))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "Producto no encontrado."

    pid, stock_actual = row
    if tipo == "entrada":
        nuevo = stock_actual + cantidad
    else:
        if cantidad > stock_actual:
            conn.close()
            return False, f"Stock insuficiente. Disponible: {stock_actual}"
        nuevo = stock_actual - cantidad

    c.execute("UPDATE productos SET cantidad = ?, actualizado = ? WHERE id = ?",
              (nuevo, datetime.now().isoformat(), pid))
    c.execute("""INSERT INTO movimientos (producto_id, tipo, cantidad, fecha)
                 VALUES (?, ?, ?, ?)""",
              (pid, tipo, cantidad, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True, f"Stock actualizado. Nuevo total: {nuevo}"


def consultar_producto(nombre):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT nombre, cantidad, precio, categoria FROM productos WHERE nombre LIKE ?",
              (f"%{nombre.lower()}%",))
    rows = c.fetchall()
    conn.close()
    return rows


def listar_productos():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT nombre, cantidad, precio, categoria FROM productos ORDER BY nombre")
    rows = c.fetchall()
    conn.close()
    return rows


def productos_bajo_stock(minimo=5):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT nombre, cantidad FROM productos WHERE cantidad <= ? ORDER BY cantidad", (minimo,))
    rows = c.fetchall()
    conn.close()
    return rows


def eliminar_producto(nombre):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM productos WHERE nombre = ?", (nombre.lower(),))
    eliminados = c.rowcount
    conn.commit()
    conn.close()
    return eliminados > 0


# ==================== CONTEO DE ALMACÉN ====================

def crear_sesion_conteo(usuario_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE conteos SET estado = 'cancelado' WHERE usuario_id = ? AND estado = 'abierto'",
              (usuario_id,))
    c.execute("""INSERT INTO conteos (usuario_id, fecha_inicio, estado)
                 VALUES (?, ?, 'abierto')""",
              (usuario_id, datetime.now().isoformat()))
    conteo_id = c.lastrowid
    conn.commit()
    conn.close()
    return conteo_id


def obtener_conteo_abierto(usuario_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""SELECT id, fecha_inicio FROM conteos
                 WHERE usuario_id = ? AND estado = 'abierto'""", (usuario_id,))
    row = c.fetchone()
    conn.close()
    return row


def registrar_conteo(conteo_id, nombre, cantidad_contada):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, cantidad FROM productos WHERE nombre = ?", (nombre.lower(),))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "Producto no encontrado."

    pid, stock_sistema = row
    c.execute("""INSERT INTO conteo_items 
        (conteo_id, producto_id, cantidad_sistema, cantidad_contada, fecha)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(conteo_id, producto_id) DO UPDATE SET
            cantidad_contada = excluded.cantidad_contada,
            fecha = excluded.fecha""",
        (conteo_id, pid, stock_sistema, cantidad_contada, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True, f"Registrado: {nombre} = {cantidad_contada} (sistema: {stock_sistema})"


def obtener_conteo_detalle(conteo_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""SELECT p.nombre, ci.cantidad_sistema, ci.cantidad_contada,
                        (ci.cantidad_contada - ci.cantidad_sistema) as diferencia
                 FROM conteo_items ci
                 JOIN productos p ON p.id = ci.producto_id
                 WHERE ci.conteo_id = ?
                 ORDER BY p.nombre""", (conteo_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def obtener_productos_no_contados(conteo_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""SELECT p.nombre FROM productos p
                 WHERE p.id NOT IN (
                     SELECT producto_id FROM conteo_items WHERE conteo_id = ?
                 )
                 ORDER BY p.nombre""", (conteo_id,))
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows


def cerrar_conteo(conteo_id, aplicar_ajustes=False):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""SELECT producto_id, cantidad_sistema, cantidad_contada
                 FROM conteo_items WHERE conteo_id = ?""", (conteo_id,))
    items = c.fetchall()

    ajustes = 0
    if aplicar_ajustes:
        for pid, sis, cont in items:
            if sis != cont:
                c.execute("""UPDATE productos 
                    SET cantidad = ?, actualizado = ? WHERE id = ?""",
                    (cont, datetime.now().isoformat(), pid))
                c.execute("""INSERT INTO movimientos 
                    (producto_id, tipo, cantidad, fecha)
                    VALUES (?, 'ajuste_conteo', ?, ?)""",
                    (pid, cont - sis, datetime.now().isoformat()))
                ajustes += 1

    c.execute("""UPDATE conteos SET estado = 'cerrado', fecha_fin = ?
                 WHERE id = ?""",
              (datetime.now().isoformat(), conteo_id))
    conn.commit()
    conn.close()
    return ajustes


def cancelar_conteo(conteo_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE conteos SET estado = 'cancelado' WHERE id = ?", (conteo_id,))
    conn.commit()
    conn.close()