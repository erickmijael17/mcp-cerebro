import os
import re
from datetime import date

from . import config


def crear_nota(curso, sesion, titulo, contenido):
    curso_limpio = _sanitizar(curso)
    carpeta_curso = os.path.join(config.VAULT_PATH, curso_limpio)
    os.makedirs(carpeta_curso, exist_ok=True)

    nombre_archivo = f"S{sesion} - {titulo}.md"
    ruta = os.path.join(carpeta_curso, nombre_archivo)

    if os.path.exists(ruta):
        raise FileExistsError(
            f"Ya existe la nota para esta sesión: {ruta}. Usa un título distinto o elimina la existente."
        )

    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)

    return {"ruta": ruta, "creado": True}


def _sanitizar(nombre):
    nombre = re.sub(r'[<>:"/\\|?*]', "", nombre).strip()
    return nombre or "Curso sin nombre"


def fecha_hoy():
    return date.today().isoformat()