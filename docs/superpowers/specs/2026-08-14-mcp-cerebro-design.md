# Diseño: MCP "Cerebro Universitario"

Fecha: 2026-08-14
Estado: Aprobado

## Propósito

Un servidor MCP que conecta a opencode con el vault de Obsidian
`D:\UPeU\Cerebro universitario`. Permite grabar la voz del docente desde el
micrófono de la laptop, transcribirla localmente con Whisper y crear notas de
resumen por sesión, organizadas por curso.

## Decisiones clave

- Transcripción: Whisper local (`faster-whisper`, modelo `small`).
- Flujo: grabar toda la clase y procesar al final.
- Nota: una nota por sesión con frontmatter + resumen + puntos clave + transcripción.
- Escritura: directa al vault (funciona con Obsidian abierto o cerrado).
- Resumen: lo genera el modelo de opencode a partir de la transcripción.
- Curso/sesión: indicados manualmente al iniciar la grabación.

## Arquitectura

```
┌───────────────┐   MCP (stdio)   ┌───────────────────────────────┐
│    opencode   │ ──────────────▶ │  mcp-cerebro (Python)         │
└───────────────┘                 │  ├─ iniciar_grabacion         │
        │                         │  ├─ detener_grabacion         │
        │ (resumen generado       │  ├─ transcribir_audio         │
        │  por el modelo)         │  └─ crear_nota                │
        ▼                         └──────────────┬────────────────┘
  Escribe .md con resumen                       │ graba audio (micrófono)
        │                                       ▼
        ▼                              faster-whisper (transcripción)
  D:\UPeU\Cerebro universitario\
      <Curso>\S<N> - Título.md
```

## Componentes

1. `mcp_cerebro/server.py` — servidor MCP (stdio) con las 4 herramientas.
2. `mcp_cerebro/audio.py` — captura de micrófono a `.wav` temporal.
3. `mcp_cerebro/transcripcion.py` — wrapper de `faster-whisper`.
4. `mcp_cerebro/vault.py` — escritura de notas en el vault.
5. `mcp_cerebro/config.py` — rutas del vault, carpeta temporal, modelo.
6. `opencode.json` (config global) — registro del servidor MCP.

## Herramientas MCP

| Herramienta            | Entrada                         | Qué hace                                        |
|------------------------|---------------------------------|-------------------------------------------------|
| `iniciar_grabacion`    | `curso`, `sesion`               | Empieza a grabar el micrófono en `temporal/`.   |
| `detener_grabacion`    | —                               | Detiene y guarda el `.wav`; devuelve duración.  |
| `transcribir_audio`    | `archivo` (opcional)            | Transcribe con Whisper; devuelve texto y segmentos. |
| `crear_nota`           | `curso`, `sesion`, `titulo`, `contenido` | Escribe `S<N> - <Título>.md` en la carpeta del curso. |

## Flujo de uso

1. En clase: "inicia grabación de Sistemas Operativos, sesión 2" → graba.
2. Al terminar: "detén la grabación y crea las notas" → transcribe, opencode
   resume, y `crear_nota` escribe el archivo.

## Formato de nota generada

```markdown
---
curso: Sistemas Operativos
sesion: 2
fecha: 2026-08-14
duracion: 75min
tags: [clase, sistemas-operativos]
---

# Sesión 2 - <Título>

## Resumen ejecutivo
...

## Puntos clave
- ...

## Términos importantes
- ...

## Transcripción completa
<texto transcrito>
```

## Manejo de errores

- Micrófono ocupado/ausente → error claro al iniciar.
- Grabación larga → el MCP divide el audio y procesa por partes.
- Vault/carpeta inexistente → se crean automáticamente.
- Whisper tarda en cargar el modelo la primera vez → se reporta como "preparando modelo".

## Dependencias

- `mcp`
- `sounddevice`
- `numpy`
- `scipy`
- `faster-whisper`

## Ubicación

- Proyecto: `D:\UPeU\mcp-cerebro\` (fuera del vault para no ensuciar Obsidian).
- Vault: `D:\UPeU\Cerebro universitario\`.