from datetime import datetime

from mcp_cerebro import config


def construir_contenido(curso, sesion, titulo, resumen, transcripcion, duracion_seg=None):
    """Arma el Markdown de la nota de sesión según el formato del spec."""
    fecha = datetime.now().strftime("%Y-%m-%d")
    duracion = _formatear_duracion(duracion_seg) if duracion_seg else "N/D"

    tags = [curso.lower().replace(" ", "-")]

    partes = [
        "---",
        f"curso: {curso}",
        f"sesion: {sesion}",
        f"fecha: {fecha}",
        f"duracion: {duracion}",
        f"tags: {tags}",
        "---",
        "",
        f"# Sesión {sesion} - {titulo}",
        "",
    ]

    if resumen:
        partes.append(resumen.strip())
        partes.append("")

    partes.append("## Transcripción completa")
    partes.append("")
    partes.append(transcripcion.strip() if transcripcion else "_Sin transcripción disponible_")
    partes.append("")

    return "\n".join(partes)


def _formatear_duracion(segundos):
    minutos = int(segundos // 60)
    seg = int(segundos % 60)
    if minutos >= 60:
        horas = minutos // 60
        minutos = minutos % 60
        return f"{horas}h {minutos}min"
    return f"{minutos}min {seg}s"
