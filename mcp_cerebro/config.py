import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VAULT_PATH = os.environ.get(
    "CEREBRO_VAULT_PATH", r"D:\UPeU\Cerebro universitario"
)

TEMP_DIR = os.environ.get(
    "CEREBRO_TEMP_DIR", os.path.join(PROJECT_DIR, "temporal")
)

WHISPER_MODEL = os.environ.get("CEREBRO_WHISPER_MODEL", "small")

SAMPLE_RATE = 16000


def ensure_temp_dir():
    os.makedirs(TEMP_DIR, exist_ok=True)
    return TEMP_DIR
