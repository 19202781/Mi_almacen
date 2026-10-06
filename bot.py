import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)
import config
import database as db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


def autorizado(func):
    """Decorador para verificar que el usuario esté autorizado."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if uid not in config.USUARIOS_AUTORIZADOS:
            await update.message.reply_text("⛔ No estás autorizado para usar este bot.")
            return
        return await func(update, context)
    return wrapper


@autorizado
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📦 *Bot de Inventario de Almacén*\n\n"
        "➕ /agregar `nombre cantidad precio`\n"
        "📥 /entrada `nombre cantidad` — Añadir stock\n"
        "📤 /salida `nombre cantidad` — Retirar stock\n"
        "🔍 /consultar `nombre`\n"
        "📋 /listar — Todo el inventario\n"
        "⚠️ /bajo — Productos con stock bajo\n"
        "🗑️ /eliminar `nombre`\n\n"
        "📝 *Conteo de almacén:*\n"
        "🔢 /conteo — Iniciar conteo físico\n"
        "✏️ /contar `nombre cantidad` — Registrar cantidad\n"
        "📊 /estadoconteo — Ver progreso\n"
        "✅ /cerrarconteo — Finalizar y ajustar\n"
        "❌ /cancelarconteo — Descartar\n\n"
        "❓ /ayuda"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


@autorizado
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


@autorizado
async def agregar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nombre = context.args[0]
        cantidad = int(context.args[1])
        precio = float(context.args[2])
        categoria = context.args[3] if len(context.args) > 3 else "general"
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Uso: `/agregar nombre cantidad precio [categoria]`\n"
            "Ej: `/agregar tornillos 100 0.25 ferreteria`",
            parse_mode="Markdown"
        )
        return

    ok, msg = db.agregar_producto(nombre, cantidad, precio, categoria)
    await update.message.reply_text(("✅ " if ok else "❌ ") + msg)


@autorizado
async def entrada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _movimiento(update, context, "entrada")


@autorizado
async def salida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _movimiento(update, context, "salida")


async def _movimiento(update, context, tipo):
    try:
        nombre = context.args[0]
        cantidad = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text(f"Uso: `/{tipo} nombre cantidad`", parse_mode="Markdown")
        return
    ok, msg = db.actualizar_stock(nombre, cantidad, tipo)
    await update.message.reply_text(("✅ " if ok else "❌ ") + msg)


@autorizado
async def consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: `/consultar nombre`", parse_mode="Markdown")
        return
    nombre = " ".join(context.args)
    rows = db.consultar_producto(nombre)
    if not rows:
        await update.message.reply_text("❌ No se encontraron productos.")
        return
    txt = "🔍 *Resultados:*\n\n"
    for n, cant, precio, cat in rows:
        txt += f"• *{n}* — {cant} uds | ${precio:.2f} | _{cat}_\n"
    await update.message.reply_text(txt, parse_mode="Markdown")


@autorizado
async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.listar_productos()
    if not rows:
        await update.message.reply_text("📭 El inventario está vacío.")
        return

    txt = "📋 *Inventario:*\n\n"
    for n, cant, precio, cat in rows:
        alerta = " ⚠️" if cant <= config.STOCK_MINIMO else ""
        txt += f"• *{n}*: {cant} uds (${precio:.2f}) [{cat}]{alerta}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")


@autorizado
async def bajo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.productos_bajo_stock(config.STOCK_MINIMO)
    if not rows:
        await update.message.reply_text("✅ No hay productos con stock bajo.")
        return
    txt = f"⚠️ *Productos con stock ≤ {config.STOCK_MINIMO}:*\n\n"
    for n, cant in rows:
        txt += f"• *{n}*: {cant} uds\n"
    await update.message.reply_text(txt, parse_mode="Markdown")


@autorizado
async def eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: `/eliminar nombre`", parse_mode="Markdown")
        return
    nombre = " ".join(context.args)
    if db.eliminar_producto(nombre):
        await update.message.reply_text(f"🗑️ Producto '{nombre}' eliminado.")
    else:
        await update.message.reply_text("❌ Producto no encontrado.")


# ==================== CONTEO DE ALMACÉN ====================

@autorizado
async def conteo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    abierto = db.obtener_conteo_abierto(uid)
    if abierto:
        await update.message.reply_text(
            f"⚠️ Ya tienes un conteo abierto (#{abierto[0]}).\n"
            f"Ciérralo con /cerrarconteo o cancélalo con /cancelarconteo."
        )
        return

    conteo_id = db.crear_sesion_conteo(uid)
    pendientes = db.obtener_productos_no_contados(conteo_id)

    txt = (
        f"📋 *Conteo de almacén iniciado* (#{conteo_id})\n\n"
        f"Productos a contar: *{len(pendientes)}*\n\n"
        "Ingresa las cantidades con:\n"
        "`/contar nombre cantidad`\n"
        "Ej: `/contar tornillos 95`\n\n"
        "Otros comandos:\n"
        "• /estadoconteo — Ver progreso\n"
        "• /cerrarconteo — Finalizar y ver diferencias\n"
        "• /cancelarconteo — Descartar sin cambios"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")


@autorizado
async def contar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    abierto = db.obtener_conteo_abierto(uid)
    if not abierto:
        await update.message.reply_text("❌ No hay un conteo abierto. Usa /conteo para iniciar uno.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso: `/contar nombre cantidad`\nEj: `/contar tornillos 95`",
            parse_mode="Markdown"
        )
        return

    try:
        cantidad = int(context.args[-1])
    except ValueError:
        await update.message.reply_text("❌ La cantidad debe ser un número entero.")
        return

    nombre = " ".join(context.args[:-1])
    conteo_id = abierto[0]
    ok, msg = db.registrar_conteo(conteo_id, nombre, cantidad)

    if ok:
        pendientes = db.obtener_productos_no_contados(conteo_id)
        contados = len(db.obtener_conteo_detalle(conteo_id))
        await update.message.reply_text(
            f"✅ {msg}\n\n"
            f"Progreso: {contados} productos contados\n"
            f"Pendientes: {len(pendientes)}"
        )
    else:
        await update.message.reply_text(f"❌ {msg}")


@autorizado
async def estado_conteo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    abierto = db.obtener_conteo_abierto(uid)
    if not abierto:
        await update.message.reply_text("❌ No hay conteo abierto.")
        return

    conteo_id = abierto[0]
    items = db.obtener_conteo_detalle(conteo_id)
    pendientes = db.obtener_productos_no_contados(conteo_id)

    if not items:
        await update.message.reply_text(
            f"📋 Conteo #{conteo_id}: aún no has contado ningún producto.\n"
            f"Productos totales: {len(pendientes)}"
        )
        return

    txt = f"📊 *Estado del conteo #{conteo_id}*\n\n"
    diferencias = 0
    for nombre, sis, cont, dif in items:
        if dif == 0:
            icono = "✅"
        elif dif > 0:
            icono = "➕"
            diferencias += 1
        else:
            icono = "➖"
            diferencias += 1

        txt += f"{icono} *{nombre}*: sistema {sis} → contado {cont} ({dif:+d})\n"

    txt += f"\n📌 Contados: {len(items)} | Pendientes: {len(pendientes)}"
    txt += f"\n⚠️ Diferencias: {diferencias}"
    await update.message.reply_text(txt, parse_mode="Markdown")


@autorizado
async def cerrar_conteo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    abierto = db.obtener_conteo_abierto(uid)
    if not abierto:
        await update.message.reply_text("❌ No hay conteo abierto.")
        return

    conteo_id = abierto[0]
    items = db.obtener_conteo_detalle(conteo_id)
    pendientes = db.obtener_productos_no_contados(conteo_id)

    if not items:
        await update.message.reply_text(
            "⚠️ No has contado ningún producto. Usa /cancelarconteo para descartar."
        )
        return

    ajustes = db.cerrar_conteo(conteo_id, aplicar_ajustes=True)

    txt = f"✅ *Conteo #{conteo_id} cerrado*\n\n"
    txt += f"📦 Productos contados: {len(items)}\n"
    txt += f"🔧 Ajustes aplicados al stock: {ajustes}\n"

    if pendientes:
        txt += f"\n⚠️ *No contados* ({len(pendientes)}):\n"
        for p in pendientes[:15]:
            txt += f"• {p}\n"
        if len(pendientes) > 15:
            txt += f"... y {len(pendientes)-15} más\n"

    difs = [i for i in items if i[3] != 0]
    if difs:
        txt += f"\n📊 *Diferencias encontradas:*\n"
        for nombre, sis, cont, dif in difs:
            txt += f"• *{nombre}*: {sis} → {cont} ({dif:+d})\n"
    else:
        txt += "\n✨ ¡Sin diferencias! El inventario cuadra perfecto."

    await update.message.reply_text(txt, parse_mode="Markdown")


@autorizado
async def cancelar_conteo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    abierto = db.obtener_conteo_abierto(uid)
    if not abierto:
        await update.message.reply_text("❌ No hay conteo abierto.")
        return

    db.cancelar_conteo(abierto[0])
    await update.message.reply_text(f"🗑️ Conteo #{abierto[0]} cancelado. Sin cambios en el inventario.")


def main():
    db.init_db()
    app = Application.builder().token(config.TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("agregar", agregar))
    app.add_handler(CommandHandler("entrada", entrada))
    app.add_handler(CommandHandler("salida", salida))
    app.add_handler(CommandHandler("consultar", consultar))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CommandHandler("bajo", bajo))
    app.add_handler(CommandHandler("eliminar", eliminar))
    app.add_handler(CommandHandler("conteo", conteo))
    app.add_handler(CommandHandler("contar", contar))
    app.add_handler(CommandHandler("estadoconteo", estado_conteo))
    app.add_handler(CommandHandler("cerrarconteo", cerrar_conteo_cmd))
    app.add_handler(CommandHandler("cancelarconteo", cancelar_conteo_cmd))

    print("🤖 Bot iniciado... Presiona Ctrl+C para detenerlo.")
    app.run_polling()


if __name__ == "__main__":
    main()