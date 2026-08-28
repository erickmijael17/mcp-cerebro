import os
import threading
import time
from typing import Callable, Optional

from faster_whisper import WhisperModel

from . import config

# --- Cache thread-safe por (modelo, compute_type, cpu_threads, num_workers) ---
_model_cache: dict = {}
_model_cache_lock = threading.Lock()
_cancel_requested = threading.Event()

# Alias amigables -> nombre real faster-whisper
_MODEL_ALIASES = {
    "distil-small": "distil-small.en",
    "distil-medium": "distil-medium.en",
    "distil-large": "distil-large-v3",
}

# Intento lazy de BatchedInferencePipeline
_BatchedPipeline = None
try:
    from faster_whisper import BatchedInferencePipeline  # type: ignore

    _BatchedPipeline = BatchedInferencePipeline
except Exception:
    _BatchedPipeline = None


def _normalizar_modelo(nombre: str) -> str:
    nombre = nombre.strip()
    return _MODEL_ALIASES.get(nombre, nombre)


def _resolver_modelo(nombre: Optional[str] = None) -> str:
    raw = nombre or config.WHISPER_MODEL
    norm = _normalizar_modelo(raw)
    # Validación suave: advierte pero permite cualquier string (para modelos locales/path)
    if norm not in config.SUPPORTED_MODELS and not os.path.exists(norm):
        # Permite rutas locales o huggingface ids custom, no bloquea
        pass
    return norm


def _get_model(modelo: Optional[str] = None):
    """Obtiene (o crea) WhisperModel cacheado thread-safe."""
    modelo_norm = _resolver_modelo(modelo)
    compute = config.WHISPER_COMPUTE_TYPE
    cpu_threads = config.WHISPER_CPU_THREADS
    num_workers = config.WHISPER_NUM_WORKERS
    key = (modelo_norm, compute, cpu_threads, num_workers)

    with _model_cache_lock:
        if key in _model_cache:
            return _model_cache[key]

    # Creación fuera del lock para no bloquear largo
    kwargs = dict(
        device="cpu",
        compute_type=compute,
        download_root=os.path.join(config.TEMP_DIR, "models"),
    )
    if cpu_threads:
        kwargs["cpu_threads"] = cpu_threads
    if num_workers != 1:
        kwargs["num_workers"] = num_workers

    instance = WhisperModel(modelo_norm, **kwargs)

    with _model_cache_lock:
        # doble-check por carrera
        if key not in _model_cache:
            _model_cache[key] = instance
        else:
            # otro hilo ya creó, descartamos instancia extra
            # (no hay close explícito en WhisperModel, se deja al GC)
            instance = _model_cache[key]
    return instance


def _get_batched_model(modelo: Optional[str] = None):
    """Retorna BatchedInferencePipeline si está habilitado y disponible."""
    if not config.WHISPER_BATCHED or _BatchedPipeline is None:
        return None
    base = _get_model(modelo)
    # BatchedInferencePipeline envuelve un WhisperModel existente
    try:
        return _BatchedPipeline(model=base)
    except Exception:
        return None


def solicitar_cancelacion():
    """Solicita cancelar la transcripción en curso (usado por GUI)."""
    _cancel_requested.set()


def limpiar_cancelacion():
    _cancel_requested.clear()


def esta_cancelado() -> bool:
    return _cancel_requested.is_set()


def transcribir(
    archivo=None,
    on_progress: Optional[Callable[[int, float, float, str], None]] = None,
    modelo: Optional[str] = None,
    language: Optional[str] = None,
    use_batched: Optional[bool] = None,
    beam_size: Optional[int] = None,
):
    """
    Transcribe audio offline (100% local) optimizado para CPU.

    Args:
        archivo: Ruta wav. Si None, usa el más reciente en TEMP_DIR.
        on_progress: Callable(idx, end_time, total_duration, texto_parcial) para barra %.
        modelo: Override de CEREBRO_WHISPER_MODEL.
        language: Override de CEREBRO_WHISPER_LANGUAGE (default 'es').
        use_batched: Fuerza uso de BatchedInferencePipeline (None=auto según config).
        beam_size: Override de CEREBRO_WHISPER_BEAM (1=greedy rápido, 5=lento preciso).

    Returns:
        dict con archivo, duracion_audio, idioma, texto, segmentos, modelo, tiempo_transcripcion
    """
    if archivo is None:
        archivo = _buscar_audio_mas_reciente()

    if not os.path.exists(archivo):
        raise FileNotFoundError(f"No existe el archivo de audio: {archivo}")

    limpiar_cancelacion()
    t0 = time.time()

    # Resolver parámetros efectivos
    lang = language or config.WHISPER_LANGUAGE or "es"
    beam = beam_size if beam_size is not None else config.WHISPER_BEAM_SIZE
    # clamp beam 1..5
    beam = max(1, min(int(beam), 5))

    vad_params = dict(
        threshold=config.WHISPER_VAD_THRESHOLD,
        min_silence_duration_ms=config.WHISPER_VAD_MIN_SILENCE_MS,
        speech_pad_ms=config.WHISPER_VAD_SPEECH_PAD_MS,
    )

    modelo_efectivo = _resolver_modelo(modelo)

    # Decidir batched
    batched_enabled = config.WHISPER_BATCHED if use_batched is None else bool(use_batched)
    batched = None
    if batched_enabled:
        batched = _get_batched_model(modelo)
    # Fallback a modelo estándar si batched no disponible
    model = None
    if batched is not None:
        # batched usará su modelo interno, pero necesitamos referencia para info
        model_ref = batched.model  # type: ignore
    else:
        model = _get_model(modelo)
        model_ref = model

    # Parámetros comunes para ambos pipelines
    transcribe_kwargs = dict(
        language=lang,
        task="transcribe",
        vad_filter=True,
        vad_parameters=vad_params,
        beam_size=beam,
        condition_on_previous_text=config.WHISPER_CONDITION_PREVIOUS,
        # Temperatura fija 0 para greedy rápido; evita reintentos con otras temps
        temperature=0.0,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        # chunk_length acelera y permite progreso por chunks; None = auto VAD
        chunk_length=config.WHISPER_CHUNK_LENGTH_INT,
    )

    if batched is not None:
        # BatchedInferencePipeline exige vad_filter=True y maneja chunk_length internamente
        # sin condition_on_previous_text (siempre False en su impl)
        # Añadimos batch_size y word_timestamps=False para velocidad
        segments, info = batched.transcribe(
            archivo,
            batch_size=config.WHISPER_BATCH_SIZE,
            **transcribe_kwargs,
        )
    else:
        segments, info = model.transcribe(archivo, **transcribe_kwargs)

    # Recolección con progreso y soporte cancelación
    texto = []
    segmentos = []
    total_dur = getattr(info, "duration", 0) or 0
    # duration_after_vad es más precisa para progreso
    dur_vad = getattr(info, "duration_after_vad", total_dur) or total_dur
    denom = dur_vad if dur_vad > 0 else (total_dur if total_dur > 0 else 1.0)

    for idx, seg in enumerate(segments):
        if esta_cancelado():
            raise RuntimeError("Transcripción cancelada por el usuario.")
        t = seg.text.strip()
        texto.append(t)
        segmentos.append(
            {
                "inicio": round(seg.start, 2),
                "fin": round(seg.end, 2),
                "texto": t,
            }
        )
        if on_progress is not None:
            try:
                # progreso 0..1 basado en timestamp actual
                prog = min(seg.end / denom, 1.0) if denom else 0.0
                on_progress(idx + 1, seg.end, total_dur, t)
            except Exception:
                pass

    texto_final = " ".join(texto)
    elapsed = time.time() - t0
    limpiar_cancelacion()

    return {
        "archivo": archivo,
        "duracion_audio": round(total_dur, 2),
        "duracion_vad": round(dur_vad, 2) if dur_vad else round(total_dur, 2),
        "idioma": getattr(info, "language", lang),
        "idioma_prob": round(getattr(info, "language_probability", 1.0), 3),
        "texto": texto_final,
        "segmentos": segmentos,
        "modelo": modelo_efectivo,
        "compute_type": config.WHISPER_COMPUTE_TYPE,
        "beam_size": beam,
        "batched": batched is not None,
        "tiempo_transcripcion": round(elapsed, 2),
        "rtf": round(elapsed / total_dur, 3) if total_dur > 0 else None,
    }


def listar_modelos():
    """Lista modelos disponibles y su tamaño estimado."""
    try:
        from faster_whisper.utils import available_models

        return available_models()
    except Exception:
        return sorted(config.SUPPORTED_MODELS)


def descargar_modelo(nombre: str):
    """Precarga un modelo offline (útil para preparar equipo sin internet)."""
    modelo_norm = _resolver_modelo(nombre)
    # Fuerza creación y cacheo
    _get_model(modelo_norm)
    return {"modelo": modelo_norm, "ok": True, "path": os.path.join(config.TEMP_DIR, "models")}


def _buscar_audio_mas_reciente():
    if not os.path.isdir(config.TEMP_DIR):
        raise FileNotFoundError(
            "No hay grabaciones en la carpeta temporal. Inicia una grabación primero."
        )
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
