import os
import time

from faster_whisper import WhisperModel

from . import config

_model = None
_model_lock = False


def _get_model():
    global _model
    if _model is None:
        _model = WhisperModel(
            config.WHISPER_MODEL,
            device="cpu",
            compute_type="int8",
            download_root=os.path.join(config.TEMP_DIR, "models"),
        )
    return _model


def transcribir(archivo=None):
    if archivo is None:
        archivo = _buscar_audio_mas_reciente()

    if not os.path.exists(archivo):
        raise FileNotFoundError(f"No existe el archivo de audio: {archivo}")

    model = _get_model()
    segments, info = model.transcribe(
        archivo,
        language="es",
        vad_filter=True,
        beam_size=5,
    )

    texto = []
    segmentos = []
    for seg in segments:
        texto.append(seg.text.strip())
        segmentos.append(
            {
                "inicio": round(seg.start, 2),
                "fin": round(seg.end, 2),
                "texto": seg.text.strip(),
            }
        )

    return {
        "archivo": archivo,
        "duracion_audio": round(info.duration, 2),
        "idioma": info.language,
        "texto": " ".join(texto),
        "segmentos": segmentos,
    }


def _buscar_audio_mas_reciente():
    audios = [
        os.path.join(config.TEMP_DIR, f)
        for f in os.listdir(config.TEMP_DIR)
        if f.lower().endswith(".wav")
    ]
    if not audios:
        raise FileNotFoundError(
            "No hay grabaciones en la carpeta temporal. Inicia una grabación primero."
        )
    return max(audios, key=os.path.getmtime)