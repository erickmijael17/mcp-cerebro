# mcp-cerebro

Sistema que conecta tu vault de Obsidian con grabación, transcripción y resumen
de las clases de tu docente. Incluye **dos formas de uso**:

1. **Interfaz gráfica (GUI)** — recomendada. App de escritorio con botones, sin
   tocar la terminal. Ideal si no quieres usar opencode directamente.
2. **MCP server** — conecta opencode (terminal) con el vault para el mismo flujo.

## Requisitos

- Python 3.10+
- Micrófono funcional en la laptop

## Instalación (todo queda en D:, sin usar disco C)

```powershell
cd D:\UPeU\mcp-cerebro
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Configuración en opencode

El servidor se registra en `C:\Users\USUARIO\.config\opencode\opencode.json` (config global de opencode, requerida ahí para que lo cargue; solo apunta a rutas de D:):

```json
{
  "mcp": {
    "cerebro": {
      "type": "local",
      "command": ["D:\\UPeU\\mcp-cerebro\\.venv\\Scripts\\python.exe", "D:\\UPeU\\mcp-cerebro\\run_server.py"],
      "enabled": true,
      "environment": {
        "CEREBRO_VAULT_PATH": "D:\\UPeU\\Cerebro universitario",
        "CEREBRO_WHISPER_MODEL": "small",
        "CEREBRO_TEMP_DIR": "D:\\UPeU\\mcp-cerebro\\temporal"
      }
    }
  }
}
```

## Herramientas

| Herramienta          | Descripción                                              |
|----------------------|----------------------------------------------------------|
| `iniciar_grabacion`  | Inicia la grabación del micrófono (curso, sesión).       |
| `detener_grabacion`  | Detiene y guarda el audio `.wav` temporal.               |
| `transcribir_audio`  | Transcribe con Whisper local (español).                  |
| `crear_nota`         | Escribe `S<N> - Título.md` en la carpeta del curso.      |

## Flujo de uso

1. En clase: *"inicia grabación de Sistemas Operativos, sesión 2"*.
2. Al terminar: *"detén la grabación y crea las notas"*.

## Variables de entorno

| Variable              | Default                          | Descripción                          |
|-----------------------|----------------------------------|--------------------------------------|
| `CEREBRO_VAULT_PATH`  | `D:\UPeU\Cerebro universitario`  | Ruta del vault de Obsidian.          |
| `CEREBRO_TEMP_DIR`    | `D:\UPeU\mcp-cerebro\temporal`   | Carpeta para audios y modelos.       |
| `CEREBRO_WHISPER_MODEL` | `small`                        | Modelo Whisper: `small`, `medium`.   |

## Guía de ejecución

### 0. Interfaz gráfica (GUI) — la forma más simple

La GUI usa **Tkinter** (incluido con Python, sin dependencias extra) y llama a
**opencode** en segundo plano para generar el resumen. No necesitas abrir la terminal.

1. Doble clic en `run_gui.bat` (o crea un acceso directo en el escritorio a ese archivo).
2. En la ventana, escribe **curso**, **sesión** y **título** de la sesión.
3. Clic **Grabar** para empezar a capturar el audio y **Detener** al terminar la clase.
4. Clic **Transcribir** (usa Whisper local, como el MCP).
5. Clic **Generar resumen** (opencode resume la transcripción; la primera vez tarda un poco).
6. Revisa el texto y clic **Guardar nota** → se escribe en el vault de Obsidian.
7. Clic **Abrir vault** para verla en Obsidian.

> Requisito: opencode debe estar instalado y en el `PATH` (p. ej. instalado por npm).
> El resumen se genera con el modelo configurado en tu opencode.

### 1. Primera vez (solo si reinstalaste o cambiaste de PC)

```powershell
cd D:\UPeU\mcp-cerebro
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

En esta PC ya está hecho: el venv, las dependencias y el modelo Whisper están descargados en `D:`.

### 2. Arrancar opencode

Reinicia opencode para que cargue el MCP `cerebro` (ya registrado en la config global con `enabled: true`). Se inicia automáticamente.

### 3. Probar que el MCP responda

Pregunta en opencode: *"¿Qué herramientas del MCP cerebro están disponibles?"* Debería listar
`iniciar_grabacion`, `detener_grabacion`, `transcribir_audio` y `crear_nota`.

### 4. Durante la clase

1. Al empezar: *"inicia grabación de Sistemas Operativos, sesión 2"*.
2. Al terminar: *"detén la grabación y crea las notas de la clase"*.
   - El MCP transcribe con Whisper, opencode genera el resumen y escribe
     `S2 - Título.md` en `D:\UPeU\Cerebro universitario\Sistemas Operativos\`.

### 5. Ver el resultado

Abre Obsidian y la nota aparecerá en la carpeta del curso. El audio queda en
`D:\UPeU\mcp-cerebro\temporal\`.

### Diagnóstico rápido

| Problema | Solución |
|---|---|
| MCP no aparece en opencode | Reinicia opencode; revisa `C:\Users\USUARIO\.config\opencode\opencode.json` |
| La GUI no abre | Ejecuta `run_gui.bat` con doble clic; si no, abre una terminal y corre `.venv\Scripts\python.exe cerebro_app\main.py` |
| "No se encontró opencode" al resumir | Instala opencode o agrégalo al `PATH`; reinicia la GUI |
| El resumen tarda | Es normal; opencode está en segundo plano. Asegúrate de tener modelo/config de opencode activos |
| "No se pudo acceder al micrófono" | Cierra apps que usen el micrófono (Zoom, Teams); verifica que no esté silenciado |
| "La grabación no contiene voz" | Acerca el micrófono a tu docente; sube el volumen de captura |
| Transcripción lenta | Es normal en CPU (modelo `small`); para mayor rapidez usa `tiny` |

## Notas

- La primera transcripción descarga el modelo (`small` ≈ 460 MB) a `temporal/models`, dentro del proyecto (no al disco C).
- Si el audio dura más de ~30 min, Whisper lo procesa por partes automáticamente.
- **Config global de opencode:** se eliminó la variable `environment.PATH` del MCP `octave`
  (estaba deshabilitado) porque `{env:PATH}` rompía `opencode run` con
  `InvalidEscapeCharacter`. Si vuelves a habilitar octave, ajusta esa entrada.