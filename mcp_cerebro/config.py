import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VAULT_PATH = os.environ.get(
    "CEREBRO_VAULT_PATH", r"D:\UPeU\Cerebro universitario"
)

TEMP_DIR = os.environ.get(
    "CEREBRO_TEMP_DIR", os.path.join(PROJECT_DIR, "temporal")
)

WHISPER_MODEL = os.environ.get("CEREBRO_WHISPER_MODEL", "small")

# --- Transcripción offline rápida ---
# Modelos soportados: tiny, tiny.en, base, small, medium, large-v3, large-v3-turbo,
# distil-small.en, distil-medium.en, distil-large-v2, distil-large-v3
WHISPER_COMPUTE_TYPE = os.environ.get("CEREBRO_WHISPER_COMPUTE", "int8")
WHISPER_BEAM_SIZE = int(os.environ.get("CEREBRO_WHISPER_BEAM", "1"))
WHISPER_BATCHED = os.environ.get("CEREBRO_WHISPER_BATCHED", "1").strip().lower() not in ("0", "false", "no")
WHISPER_BATCH_SIZE = int(os.environ.get("CEREBRO_WHISPER_BATCH_SIZE", "8"))
WHISPER_CPU_THREADS = int(os.environ.get("CEREBRO_WHISPER_CPU_THREADS", "0"))  # 0 = auto
WHISPER_NUM_WORKERS = int(os.environ.get("CEREBRO_WHISPER_NUM_WORKERS", "1"))
# VAD tuning para clases (silencios largos entre frases)
WHISPER_VAD_MIN_SILENCE_MS = int(os.environ.get("CEREBRO_VAD_MIN_SILENCE_MS", "500"))
WHISPER_VAD_SPEECH_PAD_MS = int(os.environ.get("CEREBRO_VAD_SPEECH_PAD_MS", "400"))
WHISPER_VAD_THRESHOLD = float(os.environ.get("CEREBRO_VAD_THRESHOLD", "0.5"))
# condition_on_previous_text=False reduce alucinaciones en clases largas y acelera
WHISPER_CONDITION_PREVIOUS = os.environ.get("CEREBRO_WHISPER_CONDITION_PREVIOUS", "0").strip().lower() in ("1", "true", "yes")
# Lenguaje fijo para no re-detectar (acelera ~5s al inicio)
WHISPER_LANGUAGE = os.environ.get("CEREBRO_WHISPER_LANGUAGE", "es")
# chunk_length fuerza división en chunks de 30s (None = auto VAD)
WHISPER_CHUNK_LENGTH = os.environ.get("CEREBRO_WHISPER_CHUNK_LENGTH", "")
try:
    WHISPER_CHUNK_LENGTH_INT = int(WHISPER_CHUNK_LENGTH) if WHISPER_CHUNK_LENGTH.strip() else None
except ValueError:
    WHISPER_CHUNK_LENGTH_INT = None

SAMPLE_RATE = 16000

# Whitelist para validar CEREBRO_WHISPER_MODEL y sugerir alternativas rápidas
SUPPORTED_MODELS = {
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3", "large",
    "large-v3-turbo", "turbo",
    "distil-small.en", "distil-medium.en", "distil-large-v2", "distil-large-v3", "distil-large-v3.5",
    # aliases amigables
    "distil-small", "distil-medium", "distil-large",
}


def ensure_temp_dir():
    os.makedirs(TEMP_DIR, exist_ok=True)
    return TEMP_DIR
