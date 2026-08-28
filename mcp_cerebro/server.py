import os
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from . import config, vault
from .audio import Recorder

mcp = FastMCP("mcp-cerebro")

_recorder = Recorder()


def _nombre_audio(curso, sesion):
    config.ensure_temp_dir()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    nombre = f"{_limpiar(curso)}-S{sesion}-{timestamp}.wav"
    return os.path.join(config.TEMP_DIR, nombre)


def _limpiar(texto):
    import re

    return re.sub(r'[<>:"/\\|?* ]+', "-", texto.strip()).strip("-")


@mcp.tool()
def iniciar_grabacion(curso: str, sesion: int) -> str:
    """Inicia la grabación de audio desde el micrófono para una sesión de clase.

    Args:
        curso: Nombre del curso (ej. "Sistemas Operativos").
        sesion: Número de sesión (ej. 2).
    """
    if _recorder.active:
        return "ERROR: Ya hay una grabación en curso. Usa detener_grabacion primero."

    _recorder.start()
    return f"Grabación iniciada para {curso} - Sesión {sesion}. Audio guardándose en {config.TEMP_DIR}. Detén la grabación al terminar la clase."


@mcp.tool()
def detener_grabacion(curso: str, sesion: int) -> str:
    """Detiene la grabación activa y guarda el audio como .wav temporal.

    Args:
        curso: Nombre del curso (debe coincidir con el de iniciar_grabacion).
        sesion: Número de sesión (debe coincidir con el de iniciar_grabacion).
    """
    if not _recorder.active:
        return "ERROR: No hay una grabación activa. Usa iniciar_grabacion primero."

    audio, duracion = _recorder.stop()
    ruta = _nombre_audio(curso, sesion)
    _recorder.save_wav(audio, ruta)
    minutos = int(duracion // 60)
    segundos = int(duracion % 60)
    return (
        f"Grabación detenida. Duración: {minutos}m {segundos}s. "
        f"Audio guardado en: {ruta}. "
        "Ahora ejecuta transcribir_audio para obtener el texto."
    )


@mcp.tool()
def transcribir_audio(archivo: str = None, modelo: str = None) -> str:
    """Transcribe el audio con Whisper local offline (español, rápido, sin internet).

    Optimizado: beam=1 (greedy), batched, VAD silencios 500ms, chunk 30s.
    Modelos: tiny/base/small/medium, distil-small, distil-large-v3, large-v3-turbo.
    Si no se indica archivo, usa la grabación más reciente de la carpeta temporal.

    Args:
        archivo: Ruta opcional al archivo .wav a transcribir.
        modelo: Modelo Whisper opcional (ej. "small", "distil-small", "large-v3-turbo"). Default: CEREBRO_WHISPER_MODEL.
    """
    from .transcripcion import transcribir

    try:
        resultado = transcribir(archivo, modelo=modelo)
    except Exception as exc:
        return f"ERROR: {exc}"

    texto = resultado["texto"]
    if not texto:
        return "La grabación no contiene voz detectable. Verifica que el micrófono haya capturado audio."

    rtf = resultado.get("rtf", "?")
    tiempo = resultado.get("tiempo_transcripcion", "?")
    batched = "batched" if resultado.get("batched") else "estandar"
    return (
        f"Transcripción completada ({resultado['duracion_audio']}s de audio, "
        f"{len(resultado['segmentos'])} segmentos, modelo={resultado.get('modelo')}, "
        f"{batched}, {tiempo}s, RTF={rtf}).\n\n"
        f"TEXTO:\n{texto}"
    )


@mcp.tool()
def listar_modelos() -> str:
    """Lista modelos Whisper disponibles para transcripción offline y su velocidad relativa."""
    from .transcripcion import listar_modelos

    modelos = listar_modelos()
    # Anotamos los más rápidos
    notas = {
        "tiny": "ultra rápido, menor precisión",
        "base": "rápido",
        "small": "equilibrado ⭐",
        "medium": "lento, más preciso",
        "distil-small.en": "2x más rápido que small",
        "distil-large-v3": "rápido + alta calidad",
        "large-v3-turbo": "mejor calidad, rápido",
    }
    lineas = ["Modelos disponibles (offline, sin internet):"]
    for m in modelos:
        extra = f" — {notas[m]}" if m in notas else ""
        marca = " [actual]" if m == config.WHISPER_MODEL or (config.WHISPER_MODEL == "distil-small" and m == "distil-small.en") else ""
        lineas.append(f" - {m}{extra}{marca}")
    lineas.append(f"\nActual: CEREBRO_WHISPER_MODEL={config.WHISPER_MODEL}, beam={config.WHISPER_BEAM_SIZE}, batched={config.WHISPER_BATCHED}, compute={config.WHISPER_COMPUTE_TYPE}")
    return "\n".join(lineas)


@mcp.tool()
def descargar_modelo(modelo: str) -> str:
    """Precarga un modelo Whisper para uso offline (requiere internet solo esta vez).

    Args:
        modelo: Nombre del modelo (ej. "small", "distil-small", "large-v3-turbo").
    """
    from .transcripcion import descargar_modelo as _descargar

    try:
        res = _descargar(modelo)
        return f"Modelo {res['modelo']} listo en {res['path']} (offline desde ahora)."
    except Exception as exc:
        return f"ERROR: {exc}"


@mcp.tool()
def crear_nota(curso: str, sesion: int, titulo: str, contenido: str) -> str:
    """Crea la nota de la sesión en el vault de Obsidian.

    Args:
        curso: Nombre del curso (define la carpeta).
        sesion: Número de sesión.
        titulo: Título descriptivo de la sesión.
        contenido: Contenido Markdown completo de la nota (con frontmatter y resumen).
    """
    try:
        resultado = vault.crear_nota(curso, sesion, titulo, contenido)
    except Exception as exc:
        return f"ERROR: {exc}"

    return (
        f"Nota creada: {resultado['ruta']}\n"
        "Puedes abrirla en Obsidian o revisarla directamente en el vault."
    )


if __name__ == "__main__":
    mcp.run()