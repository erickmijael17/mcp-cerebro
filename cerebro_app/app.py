import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

from mcp_cerebro import config, vault
from mcp_cerebro.audio import Recorder

from .nota import construir_contenido
from .resumen import generar_resumen

_ACCIONES = {
    "inicio": "Iniciando...",
    "transcribir": "Transcribiendo con Whisper (la primera vez descarga el modelo)...",
    "resumir": "Generando resumen con opencode...",
    "guardar": "Guardando nota en Obsidian...",
}


class CerebroApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cerebro - Grabación y notas de clase")
        self.geometry("760x620")
        self.minsize(640, 520)

        self._recorder = Recorder()
        self._audio_path = None
        self._duracion = None
        self._transcripcion = ""
        self._resumen = ""
        self._cola = queue.Queue()
        self._ocupado = False

        self._construir_interfaz()
        self.after(100, self._procesar_cola)

    # ------------------------------------------------------------------ UI
    def _construir_interfaz(self):
        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)

        ttk.Label(marco, text="Curso").grid(row=0, column=0, sticky="w")
        self.var_curso = tk.StringVar()
        ttk.Entry(marco, textvariable=self.var_curso, width=30).grid(
            row=0, column=1, sticky="we", padx=6, pady=3
        )

        ttk.Label(marco, text="Sesión").grid(row=1, column=0, sticky="w")
        self.var_sesion = tk.StringVar()
        ttk.Entry(marco, textvariable=self.var_sesion, width=8).grid(
            row=1, column=1, sticky="w", padx=6, pady=3
        )

        ttk.Label(marco, text="Título de la sesión").grid(row=2, column=0, sticky="w")
        self.var_titulo = tk.StringVar()
        ttk.Entry(marco, textvariable=self.var_titulo, width=30).grid(
            row=2, column=1, sticky="we", padx=6, pady=3
        )

        botonera = ttk.Frame(marco)
        botonera.grid(row=3, column=0, columnspan=2, sticky="we", pady=8)
        self.btn_grabar = ttk.Button(botonera, text="Grabar", command=self._alternar_grabacion)
        self.btn_grabar.pack(side="left", padx=(0, 6))
        self.btn_transcribir = ttk.Button(
            botonera, text="Transcribir", command=self._iniciar_transcripcion
        )
        self.btn_transcribir.pack(side="left", padx=6)
        self.btn_resumir = ttk.Button(
            botonera, text="Generar resumen", command=self._iniciar_resumen
        )
        self.btn_resumir.pack(side="left", padx=6)
        self.btn_guardar = ttk.Button(
            botonera, text="Guardar nota", command=self._guardar_nota
        )
        self.btn_guardar.pack(side="left", padx=6)
        self.btn_abrir = ttk.Button(
            botonera, text="Abrir vault", command=self._abrir_vault
        )
        self.btn_abrir.pack(side="left", padx=6)

        self.var_estado = tk.StringVar(value="Listo.")
        ttk.Label(marco, textvariable=self.var_estado).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )

        self.progreso = ttk.Progressbar(marco, mode="indeterminate")
        self.progreso.grid(row=5, column=0, columnspan=2, sticky="we", pady=(0, 8))

        contenedor = ttk.LabelFrame(marco, text="Detalle")
        contenedor.grid(row=6, column=0, columnspan=2, sticky="nsew")
        self.texto = scrolledtext.ScrolledText(contenedor, wrap="word", font=("Consolas", 10))
        self.texto.pack(fill="both", expand=True)

        marco.columnconfigure(1, weight=1)
        marco.rowconfigure(6, weight=1)

    # ------------------------------------------------------------ Grabación
    def _alternar_grabacion(self):
        if self._recorder.active:
            self._detener_grabacion()
        else:
            self._iniciar_grabacion()

    def _iniciar_grabacion(self):
        curso = self.var_curso.get().strip()
        sesion = self.var_sesion.get().strip()
        if not curso:
            messagebox.showwarning("Falta información", "Indica el nombre del curso.")
            return
        if not sesion:
            messagebox.showwarning("Falta información", "Indica el número de sesión.")
            return

        try:
            self._recorder.start()
        except RuntimeError as exc:
            messagebox.showerror("Micrófono", str(exc))
            return

        self.btn_grabar.config(text="Detener")
        self.var_estado.set(
            f"Grabando {curso} - Sesión {sesion}... "
            f"(audio temporal en {config.TEMP_DIR})"
        )
        self._log(f"[{self._hora()}] Grabación iniciada para {curso} - Sesión {sesion}.")

    def _detener_grabacion(self):
        try:
            audio, duracion = self._recorder.stop()
        except RuntimeError as exc:
            messagebox.showerror("Grabación", str(exc))
            return

        self._duracion = duracion
        self._audio_path = self._nombre_audio()
        self._recorder.save_wav(audio, self._audio_path)

        minutos = int(duracion // 60)
        segundos = int(duracion % 60)
        self.btn_grabar.config(text="Grabar")
        self.var_estado.set(f"Grabación guardada ({minutos}m {segundos}s). Ahora puedes transcribir.")
        self._log(f"[{self._hora()}] Grabación detenida ({minutos}m {segundos}s).")
        self._log(f"[{self._hora()}] Audio guardado en: {self._audio_path}")

    def _nombre_audio(self):
        config.ensure_temp_dir()
        curso = _limpiar(self.var_curso.get().strip())
        sesion = _limpiar(self.var_sesion.get().strip())
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return os.path.join(config.TEMP_DIR, f"{curso}-S{sesion}-{timestamp}.wav")

    # ---------------------------------------------------------- Transcripción
    def _iniciar_transcripcion(self):
        if self._ocupado:
            return
        if not self._audio_path:
            messagebox.showwarning(
                "Sin audio", "Primero graba y detén la grabación para tener un audio."
            )
            return
        self._set_ocupado(True, "transcribir")
        threading.Thread(target=self._tarea_transcribir, daemon=True).start()

    def _tarea_transcribir(self):
        from mcp_cerebro.transcripcion import transcribir

        try:
            resultado = transcribir(self._audio_path)
            self._cola.put({"tipo": "transcripcion", "ok": True, "datos": resultado})
        except Exception as exc:
            self._cola.put({"tipo": "transcripcion", "ok": False, "error": str(exc)})

    # ---------------------------------------------------------------- Resumen
    def _iniciar_resumen(self):
        if self._ocupado:
            return
        if not self._transcripcion:
            messagebox.showwarning("Sin transcripción", "Primero transcribe el audio.")
            return
        self._set_ocupado(True, "resumir")
        threading.Thread(target=self._tarea_resumen, daemon=True).start()

    def _tarea_resumen(self):
        try:
            resumen = generar_resumen(self._transcripcion)
            self._cola.put({"tipo": "resumen", "ok": True, "texto": resumen})
        except Exception as exc:
            self._cola.put({"tipo": "resumen", "ok": False, "error": str(exc)})

    # ------------------------------------------------------------ Guardar nota
    def _guardar_nota(self):
        curso = self.var_curso.get().strip()
        sesion = self.var_sesion.get().strip()
        titulo = self.var_titulo.get().strip()
        if not (curso and sesion):
            messagebox.showwarning("Falta información", "Indica curso y sesión.")
            return
        if not titulo:
            titulo = f"Clase {datetime.now().strftime('%Y-%m-%d')}"
        if not self._resumen:
            continuar = messagebox.askyesno(
                "Sin resumen",
                "Todavía no hay resumen. ¿Guardar la nota solo con la transcripción?",
            )
            if not continuar:
                return

        contenido = construir_contenido(
            curso,
            sesion,
            titulo,
            self._resumen,
            self._transcripcion,
            self._duracion,
        )

        try:
            sesion_int = int(sesion)
        except ValueError:
            messagebox.showerror("Sesión", "La sesión debe ser un número entero.")
            return

        try:
            resultado = vault.crear_nota(curso, sesion_int, titulo, contenido)
        except FileExistsError as exc:
            messagebox.showerror("Nota duplicada", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return

        self.var_estado.set(f"Nota creada: {resultado['ruta']}")
        self._log(f"[{self._hora()}] Nota creada: {resultado['ruta']}")
        messagebox.showinfo("Nota creada", f"Se guardó la nota en:\n{resultado['ruta']}")

    # ------------------------------------------------------------------ Vault
    def _abrir_vault(self):
        config.ensure_temp_dir()
        ruta = config.VAULT_PATH
        if not os.path.isdir(ruta):
            messagebox.showwarning(
                "Vault no encontrado",
                f"No existe la carpeta del vault:\n{ruta}\nRevisa CEREBRO_VAULT_PATH.",
            )
            return
        os.startfile(ruta)

    # ---------------------------------------------------- Estado / cola / hilos
    def _set_ocupado(self, ocupado, accion=None):
        self._ocupado = ocupado
        self.progreso.config(mode="indeterminate" if ocupado else "determinate")
        if ocupado:
            self.progreso.start(12)
            self.var_estado.set(_ACCIONES.get(accion, "Trabajando..."))
        else:
            self.progreso.stop()
            self.progreso.config(value=0)

    def _procesar_cola(self):
        try:
            while True:
                mensaje = self._cola.get_nowait()
                self._manejar_mensaje(mensaje)
        except queue.Empty:
            pass
        self.after(100, self._procesar_cola)

    def _manejar_mensaje(self, mensaje):
        tipo = mensaje["tipo"]
        if tipo == "transcripcion":
            if mensaje["ok"]:
                datos = mensaje["datos"]
                self._transcripcion = datos["texto"]
                self.texto.delete("1.0", "end")
                self.texto.insert("1.0", self._transcripcion)
                self.var_estado.set(
                    f"Transcripción lista ({datos['duracion_audio']}s de audio). Revisa y corrige el texto, luego genera el resumen."
                )
                self._log(f"[{self._hora()}] Transcripción completada ({datos['duracion_audio']}s).")
            else:
                self.var_estado.set("Error en la transcripción.")
                messagebox.showerror("Transcripción", mensaje["error"])
                self._log(f"[{self._hora()}] ERROR transcripción: {mensaje['error']}")
            self._set_ocupado(False)

        elif tipo == "resumen":
            if mensaje["ok"]:
                self._resumen = mensaje["texto"]
                self.var_estado.set("Resumen generado. Revisa el texto y guarda la nota.")
                self._log(f"[{self._hora()}] Resumen generado por opencode.")
            else:
                self.var_estado.set("Error al generar el resumen.")
                messagebox.showerror("Resumen", mensaje["error"])
                self._log(f"[{self._hora()}] ERROR resumen: {mensaje['error']}")
            self._set_ocupado(False)

    def _log(self, texto):
        self.texto.insert("end", "\n" + texto)
        self.texto.see("end")

    def _hora(self):
        return datetime.now().strftime("%H:%M:%S")


def _limpiar(texto):
    import re

    return re.sub(r'[<>:"/\\|?* ]+', "-", texto.strip()).strip("-")
