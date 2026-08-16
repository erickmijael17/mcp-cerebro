import json
import os
import shutil
import subprocess

_PROMPT_TEMPLATE = (
    "Resume la siguiente transcripcion de una clase universitaria en espanol. "
    "Responde unicamente con el resumen en este formato: "
    "## Resumen ejecutivo (2-4 parrafos), ## Puntos clave (lista con guiones), "
    "## Terminos importantes (lista con guiones, termino: definicion corta). "
    "No uses herramientas ni ejecutes comandos. "
    "Transcripcion: <<<{texto}>>>"
)


def _ruta_opencode():
    ruta = shutil.which("opencode")
    if ruta:
        return ruta
    candidata = os.path.join(
        os.environ.get("APPDATA", ""),
        "npm",
        "opencode.cmd",
    )
    if os.path.exists(candidata):
        return candidata
    raise FileNotFoundError(
        "No se encontró opencode en el PATH. Instálalo o agrégalo al PATH del sistema."
    )


def generar_resumen(texto, tiempo_maximo_seg=600):
    """Llama a `opencode run --format json` en segundo plano (sin ventana de consola)
    y devuelve el texto del resumen generado por el modelo.
    """
    if not texto or not texto.strip():
        raise ValueError("La transcripción está vacía; no hay nada que resumir.")

    prompt = _PROMPT_TEMPLATE.format(texto=texto.strip())
    comando = [_ruta_opencode(), "run", "--pure", "--format", "json", prompt]

    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        comando,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
    )

    try:
        stdout, stderr = proc.communicate(timeout=tiempo_maximo_seg)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise TimeoutError(
            f"opencode tardó más de {tiempo_maximo_seg // 60} minutos en generar el resumen."
        )

    if proc.returncode != 0:
        detalle = (stderr or stdout or "").strip()[-800:]
        raise RuntimeError(f"opencode falló al generar el resumen.\n{detalle}")

    texto_final = _extraer_texto(stdout)
    if not texto_final:
        raise RuntimeError(
            "opencode respondió sin contenido. Revisa que el modelo y la autenticación estén configurados."
        )
    return texto_final


def _extraer_texto(salida_ndjson):
    partes = []
    for linea in salida_ndjson.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            evento = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if evento.get("type") != "text":
            continue
        parte = evento.get("part") or {}
        texto = parte.get("text")
        if texto:
            partes.append(texto)
    return "\n".join(partes).strip()
