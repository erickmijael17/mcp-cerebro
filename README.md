<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/MCP-Server-7B61FF" alt="MCP Server"/>
  <img src="https://img.shields.io/badge/Whisper-Local-FF6B35" alt="Whisper local"/>
  <img src="https://img.shields.io/badge/GUI-Tkinter-3EAAE9" alt="GUI Tkinter"/>
  <img src="https://img.shields.io/badge/license-MIT-green" alt="Licencia MIT"/>
</p>

# 🧠 mcp-cerebro

> Graba, transcribe y resume tus clases para convertirlas en notas de estudio organizadas en **Obsidian** — sin depender de la nube para la transcripción.

**mcp-cerebro** captura el audio del micrófono durante una clase, lo transcribe con **Whisper local**, genera un **resumen con IA** y guarda una nota Markdown bien estructurada en tu vault de Obsidian. Tu "segundo cerebro" de estudio, listo con un par de clics.

---

## ✨ ¿Qué hace?

| Paso | Qué ocurre |
|------|------------|
| 🎙️ **Graba** | Captura la clase desde el micrófono y guarda un `.wav` temporal. |
| 📝 **Transcribe** | Convierte el audio a texto en español usando **faster-whisper** (100% local, sin subir audio a la nube). |
| 🤖 **Resume** | Un modelo de IA (a través de opencode) genera un resumen ejecutivo, puntos clave y términos importantes. |
| 🗂️ **Guarda** | Escribe una nota `S<N> - Título.md` en la carpeta del curso dentro de tu vault de Obsidian. |

### Estructura de la nota generada

```markdown
---
curso: Sistemas Operativos
sesion: 2
fecha: 2026-08-16
duracion: 75min
tags: [clase, sistemas-operativos]
---

# Sesión 2 - Procesos y Hilos

## Resumen ejecutivo
...

## Puntos clave
- ...

## Términos importantes
- **Proceso**: ...

## Transcripción completa
<texto transcrito>
```

---

## 🖥️ Dos formas de usarlo

### 1. Interfaz gráfica (GUI) — recomendada

Aplicación de escritorio con botones, ideal si no quieres tocar la terminal.

1. Lanza la app (doble clic en `run_gui.bat`).
2. Escribe **curso**, **sesión** y **título**.
3. Clic **Grabar** → captura la clase. Clic **Detener** al terminar.
4. Clic **Transcribir** → Whisper procesa el audio.
5. Clic **Generar resumen** → la IA resume la transcripción.
6. Clic **Guardar nota** → se escribe en Obsidian.

### 2. MCP server (para opencode)

Servidor [MCP](https://modelcontextprotocol.io) que expone las mismas capacidades
como herramientas para que un asistente de IA (p. ej. opencode) las use en conversación:

| Herramienta           | Descripción                                              |
|-----------------------|----------------------------------------------------------|
| `iniciar_grabacion`   | Inicia la grabación del micrófono (curso, sesión).       |
| `detener_grabacion`   | Detiene y guarda el audio `.wav` temporal.               |
| `transcribir_audio`   | Transcribe con Whisper local (español).                  |
| `crear_nota`          | Escribe `S<N> - Título.md` en la carpeta del curso.      |

---

## 🛠️ Tecnologías

| Capa            | Tecnología                                          |
|-----------------|-----------------------------------------------------|
| **Lenguaje**    | Python 3.10+                                        |
| **GUI**         | Tkinter (incluido en Python, sin dependencias extra)|
| **Transcripción**| faster-whisper (modelo Whisper `small`, local/offline)|
| **Audio**       | sounddevice + numpy + scipy                         |
| **Protocolo**   | Model Context Protocol (MCP) con FastMCP            |
| **Resumen IA**  | opencode (llamado en segundo plano, modelo a elección)|
| **Almacenamiento**| Obsidian vault (notas Markdown por curso)          |

### Estructura del proyecto

```
mcp-cerebro/
├── cerebro_app/          # Interfaz gráfica de escritorio (Tkinter)
│   ├── app.py            #   Ventana principal y flujo de la GUI
│   ├── resumen.py        #   Invocación de opencode (resumen con IA)
│   ├── nota.py           #   Construcción del Markdown de la nota
│   └── main.py           #   Punto de entrada de la GUI
├── mcp_cerebro/          # Núcleo (compartido por GUI y MCP)
│   ├── server.py         #   Servidor MCP y sus herramientas
│   ├── audio.py          #   Captura de micrófono a .wav
│   ├── transcripcion.py  #   Whisper local (español)
│   ├── vault.py          #   Escritura de notas en Obsidian
│   └── config.py         #   Configuración por variables de entorno
├── run_server.py         # Arranque del servidor MCP
├── run_gui.bat           # Lanzador de la GUI (Windows)
└── requirements.txt
```

---

## 📦 Requisitos

- **Python 3.10+**
- **Micrófono funcional**
- **opencode** instalado y en el `PATH` (solo necesario para generar el resumen; instálalo con `npm i -g opencode-ai` o desde [opencode.ai](https://opencode.ai))
- **Obsidian** (opcional, para visualizar las notas; no es obligatorio tenerlo abierto)

## 🚀 Instalación

```bash
# 1. Clona el repositorio
git clone https://github.com/erickmijael17/mcp-cerebro.git
cd mcp-cerebro

# 2. Crea y activa el entorno virtual (Windows)
python -m venv .venv
.venv\Scripts\activate

# 3. Instala las dependencias
pip install -r requirements.txt
```

La primera transcripción descarga el modelo Whisper (`small`, ≈ 460 MB) a la
carpeta temporal del proyecto. Audios largos (más de ~30 min) se procesan por partes automáticamente.

## ⚙️ Configuración

Toda la configuración se hace con **variables de entorno**:

| Variable              | Descripción                               | Default            |
|-----------------------|-------------------------------------------|--------------------|
| `CEREBRO_VAULT_PATH`  | Ruta del vault de Obsidian.               | `Cerebro universitario` (junto al proyecto) |
| `CEREBRO_TEMP_DIR`    | Carpeta para audios y modelos.            | `temporal/`        |
| `CEREBRO_WHISPER_MODEL` | Modelo Whisper: `tiny`, `small`, `medium`. | `small`          |

### Ejemplo de uso como MCP en opencode

Registra el servidor en tu configuración de opencode:

```json
{
  "mcp": {
    "cerebro": {
      "type": "local",
      "command": ["C:\\ruta\\a\\mcp-cerebro\\.venv\\Scripts\\python.exe", "C:\\ruta\\a\\mcp-cerebro\\run_server.py"],
      "enabled": true,
      "environment": {
        "CEREBRO_VAULT_PATH": "C:\\ruta\\a\\tu\\vault",
        "CEREBRO_WHISPER_MODEL": "small",
        "CEREBRO_TEMP_DIR": "C:\\ruta\\a\\mcp-cerebro\\temporal"
      }
    }
  }
}
```

---

## 🧪 Flujo de trabajo típico

1. En clase, dile a tu asistente: *"inicia grabación de Sistemas Operativos, sesión 2"*.
2. Al terminar: *"detén la grabación y crea las notas"*.
3. El sistema transcribe con Whisper, genera el resumen con IA y guarda
   `S2 - Título.md` en la carpeta del curso de tu vault.

---

## ❓ Solución de problemas

| Problema | Solución |
|----------|----------|
| La GUI no abre | Corre `.venv\Scripts\python.exe cerebro_app\main.py` desde una terminal para ver el error. |
| "No se encontró opencode" al resumir | Instala opencode o agrégalo al `PATH` y reinicia la app. |
| "No se pudo acceder al micrófono" | Cierra apps que usen el micrófono (Zoom, Teams) y verifica que no esté silenciado. |
| "La grabación no contiene voz" | Acerca el micrófono y sube el volumen de captura. |
| Transcripción lenta | Es normal en CPU con el modelo `small`; usa `tiny` para mayor velocidad. |

---

## 📄 Licencia

Distribuido bajo la licencia **MIT**. Consulta el archivo `LICENSE` para más detalles.

---

<p align="center">Hecho con ☕ y 🎧 para que estudiar sea más fácil.</p>