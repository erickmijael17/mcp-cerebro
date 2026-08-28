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
    "transcribir": "Transcribiendo... (offline, sin internet)",
    "resumir": "Generando resumen con opencode...",
    "guardar": "Guardando nota en Obsidian...",
}

# Opciones de modelo para GUI: (label visible, id faster-whisper)
_MODELOS_GUI = [
    ("tiny — ultra rápido (40 MB, ~4 min/h)", "tiny"),
    ("base — rápido (150 MB, ~8 min/h)", "base"),
    ("small — equilibrado (460 MB) ⭐ recomendado", "small"),
    ("medium — más preciso (1.5 GB, lento)", "medium"),
    ("distil-small — EN only, 2x rápido (no español)", "distil-small"),
    ("distil-large-v3 — alta calidad rápida (800 MB)", "distil-large-v3"),
    ("large-v3-turbo — mejor calidad (800 MB)", "large-v3-turbo"),
]
# Mapa label -> id
_MODELO_IDS = [m[1] for m in _MODELOS_GUI]
_MODELO_LABELS = [m[0] for m in _MODELOS_GUI]


class CerebroApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cerebro - Grabación y notas de clase")
        self.geometry("840x700")
        self.minsize(680, 580)

        self._recorder = Recorder()
        self._audio_path = None
        self._duracion = None
        self._transcripcion = ""
        self._resumen = ""
        self._cola = queue.Queue()
        self._ocupado = False
        self._progreso_val = 0

        self.var_auto_resumen = tk.BooleanVar(value=True)

        self._construir_interfaz()
        self.after(100, self._procesar_cola)

    # ------------------------------------------------------------------ UI
    def _construir_interfaz(self):
        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)

        # --- Fila 0: Curso
        ttk.Label(marco, text="Curso").grid(row=0, column=0, sticky="w")
        self.var_curso = tk.StringVar()
        self.entry_curso = ttk.Entry(marco, textvariable=self.var_curso, width=32)
        self.entry_curso.grid(row=0, column=1, sticky="we", padx=6, pady=3)

        # --- Fila 1: Sesión
        ttk.Label(marco, text="Sesión").grid(row=1, column=0, sticky="w")
        self.var_sesion = tk.StringVar()
        self.entry_sesion = ttk.Entry(marco, textvariable=self.var_sesion, width=8)
        self.entry_sesion.grid(row=1, column=1, sticky="w", padx=6, pady=3)

        # --- Fila 2: Título
        ttk.Label(marco, text="Título de la sesión").grid(row=2, column=0, sticky="w")
        self.var_titulo = tk.StringVar()
        self.entry_titulo = ttk.Entry(marco, textvariable=self.var_titulo, width=32)
        self.entry_titulo.grid(row=2, column=1, sticky="we", padx=6, pady=3)

        # --- Fila 2b: Modelo offline (nuevo)
        ttk.Label(marco, text="Modelo offline").grid(row=3, column=0, sticky="w")
        modelo_frame = ttk.Frame(marco)
        modelo_frame.grid(row=3, column=1, sticky="we", padx=6, pady=3)
        self.var_modelo = tk.StringVar(value=config.WHISPER_MODEL)
        # Normaliza alias prod: distil-small.en -> distil-small para display
        display_val = self.var_modelo.get()
        if display_val == "distil-small.en":
            display_val = "distil-small"
        # Buscar label correspondiente
        label_inicial = next((lbl for lbl, mid in _MODELOS_GUI if mid == display_val), _MODELO_LABELS[2])
        self.combo_modelo = ttk.Combobox(modelo_frame, values=_MODELO_LABELS, state="readonly", width=42)
        self.combo_modelo.set(label_inicial)
        self.combo_modelo.pack(side="left")
        # Bind cambio -> actualiza config en memoria
        self.combo_modelo.bind("<<ComboboxSelected>>", self._on_modelo_cambiado)
        ttk.Label(modelo_frame, text="  100% offline", font=("Segoe UI", 7), foreground="#616161").pack(side="left", padx=6)
        # Info batched
        batched_txt = "⚡ batched ON" if config.WHISPER_BATCHED else "batched OFF"
        self.lbl_batched = ttk.Label(modelo_frame, text=batched_txt, font=("Consolas", 7, "bold"), foreground="#2e7d32" if config.WHISPER_BATCHED else "#c62828")
        self.lbl_batched.pack(side="left", padx=6)

        # --- Fila 3: Botonera
        botonera = ttk.Frame(marco)
        botonera.grid(row=4, column=0, columnspan=2, sticky="we", pady=8)
        self.btn_grabar = ttk.Button(botonera, text="Grabar", command=self._alternar_grabacion)
        self.btn_grabar.pack(side="left", padx=(0, 6))
        self.btn_transcribir = ttk.Button(
            botonera, text="Transcribir", command=self._iniciar_transcripcion
        )
        self.btn_transcribir.pack(side="left", padx=6)
        self.btn_cancelar = ttk.Button(
            botonera, text="Cancelar", command=self._cancelar_transcripcion, state="disabled"
        )
        self.btn_cancelar.pack(side="left", padx=2)
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

        # Checkbutton pipeline automatico (requisito 3)
        self.chk_auto = ttk.Checkbutton(
            botonera, text="Resumir automáticamente al terminar", variable=self.var_auto_resumen
        )
        self.chk_auto.pack(side="left", padx=(18, 0))

        # --- Fila 4: Medidor VU (Canvas) + label nivel
        medidor_frame = ttk.LabelFrame(marco, text="Micrófono", padding=6)
        medidor_frame.grid(row=5, column=0, columnspan=2, sticky="we", pady=(2, 6))
        medidor_frame.columnconfigure(0, weight=1)

        # Canvas: barra que cambia color segun volumen
        self._canvas_meter = tk.Canvas(medidor_frame, height=20, bg="#e0e0e0", highlightthickness=1, highlightbackground="#9e9e9e")
        self._canvas_meter.grid(row=0, column=0, sticky="we", padx=(0, 6))
        # Rectangulo inicial (0 ancho)
        self._meter_bar = self._canvas_meter.create_rectangle(0, 0, 0, 20, fill="#bdbdbd", outline="")
        # Texto overlay opcional centrado
        self._meter_text = self._canvas_meter.create_text(120, 10, text="En espera", fill="#424242", font=("Segoe UI", 8))

        self.var_nivel = tk.StringVar(value="0%")
        ttk.Label(medidor_frame, textvariable=self.var_nivel, width=5, font=("Consolas", 9, "bold")).grid(row=0, column=1, sticky="e")
        ttk.Label(medidor_frame, text="VU", font=("Segoe UI", 7)).grid(row=0, column=2, sticky="e", padx=(2,0))

        # --- Fila 5: Estado muy visible
        self.var_estado = tk.StringVar(value="Listo.")
        self.lbl_estado = ttk.Label(marco, textvariable=self.var_estado, font=("Segoe UI", 10, "bold"), foreground="#1565c0")
        self.lbl_estado.grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 4))

        # --- Fila 6: Progreso (determinate para transcripción)
        progreso_frame = ttk.Frame(marco)
        progreso_frame.grid(row=7, column=0, columnspan=2, sticky="we", pady=(0, 8))
        progreso_frame.columnconfigure(0, weight=1)
        self.progreso = ttk.Progressbar(progreso_frame, mode="determinate", maximum=100)
        self.progreso.grid(row=0, column=0, sticky="we")
        self.var_progreso = tk.StringVar(value="")
        ttk.Label(progreso_frame, textvariable=self.var_progreso, width=8, font=("Consolas", 8)).grid(row=0, column=1, padx=6, sticky="e")

        # --- Fila 7: Detalle (transcripcion + logs)
        contenedor = ttk.LabelFrame(marco, text="Detalle")
        contenedor.grid(row=8, column=0, columnspan=2, sticky="nsew")
        self.texto = scrolledtext.ScrolledText(contenedor, wrap="word", font=("Consolas", 10))
        self.texto.pack(fill="both", expand=True)

        marco.columnconfigure(1, weight=1)
        marco.rowconfigure(8, weight=1)

    def _on_modelo_cambiado(self, event=None):
        label = self.combo_modelo.get()
        # buscar id
        for lbl, mid in _MODELOS_GUI:
            if lbl == label:
                self.var_modelo.set(mid)
                config.WHISPER_MODEL = mid
                self._log(f"[{self._hora()}] Modelo cambiado a: {mid} (próxima transcripción)")
                break

    def _cancelar_transcripcion(self):
        try:
            from mcp_cerebro.transcripcion import solicitar_cancelacion
            solicitar_cancelacion()
            self.var_estado.set("Cancelando transcripción...")
            self._log(f"[{self._hora()}] Solicitud de cancelación enviada.")
            self.btn_cancelar.config(state="disabled")
        except Exception as exc:
            messagebox.showerror("Cancelar", str(exc))

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

        # Preparar ruta con anticipacion para modo streaming (evita RAM)
        self._audio_path = self._nombre_audio()
        try:
            # Nuevo: streaming directo a disco -> RAM constante ~pocos KB
            self._recorder.start(path=self._audio_path)
        except RuntimeError as exc:
            self._audio_path = None
            messagebox.showerror("Micrófono", str(exc))
            return

        self.btn_grabar.config(text="Detener")
        self.var_estado.set(
            f"Grabando {curso} - Sesión {sesion}... "
            f"(streaming a {self._audio_path})"
        )
        self._log(f"[{self._hora()}] Grabación iniciada (streaming) para {curso} - Sesión {sesion}.")
        self._log(f"[{self._hora()}] Destino: {self._audio_path}")
        # Iniciar visualizador VU ciclico
        self._canvas_meter.itemconfig(self._meter_text, text="Grabando...")
        self.after(100, self._actualizar_medidor_audio)

    def _detener_grabacion(self):
        try:
            ret, duracion = self._recorder.stop()
            # ret es None en modo streaming (archivo ya en self._audio_path)
            # ret es ndarray en modo legacy -> guardar a disco
            if ret is not None:
                # Caso legacy inesperado en app (si start sin path) -> persistir ahora
                if hasattr(ret, "shape") and ret.size > 0:
                    if not self._audio_path:
                        self._audio_path = self._nombre_audio()
                    self._recorder.save_wav(ret, self._audio_path)
            # duracion precisa por muestras escritas
            self._duracion = duracion
        except RuntimeError as exc:
            messagebox.showerror("Grabación", str(exc))
            return

        minutos = int(self._duracion // 60)
        segundos = int(self._duracion % 60)
        self.btn_grabar.config(text="Grabar")
        # Reset visual medidor
        self._canvas_meter.coords(self._meter_bar, 0, 0, 0, 20)
        self._canvas_meter.itemconfig(self._meter_bar, fill="#bdbdbd")
        self._canvas_meter.itemconfig(self._meter_text, text="Guardado")
        self.var_nivel.set("0%")

        self.var_estado.set(f"Grabación guardada ({minutos}m {segundos}s).")
        self._log(f"[{self._hora()}] Grabación detenida ({minutos}m {segundos}s).")
        self._log(f"[{self._hora()}] Audio guardado en: {self._audio_path}")

        # --- Pipeline automatico: al terminar y guardar, invocar transcripcion ---
        if self._audio_path and os.path.exists(self._audio_path):
            self.var_estado.set(f"Grabación guardada ({minutos}m {segundos}s). Iniciando transcripción automática...")
            self._log(f"[{self._hora()}] Pipeline: iniciando transcripción automática...")
            # Pequeño delay para que UI refresque antes de hilo pesado
            self.after(400, self._iniciar_transcripcion)
        else:
            messagebox.showwarning("Audio no encontrado", f"No se encontró el archivo: {self._audio_path}")

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
        if not os.path.exists(self._audio_path):
            messagebox.showerror("Audio perdido", f"No existe el archivo:\n{self._audio_path}")
            return
        self._set_ocupado(True, "transcribir")
        self.progreso.config(value=0)
        self.var_progreso.set("0%")
        threading.Thread(target=self._tarea_transcribir, daemon=True).start()

    def _tarea_transcribir(self):
        from mcp_cerebro.transcripcion import transcribir

        # Aplica modelo seleccionado en GUI (si cambió)
        modelo_elegido = self.var_modelo.get().strip()
        if modelo_elegido:
            config.WHISPER_MODEL = modelo_elegido

        def on_progress(idx, end_time, total_dur, snippet):
            try:
                pct = int(min(100, max(0, end_time / total_dur * 100))) if total_dur else 0
                # Enviar progreso a cola (thread-safe)
                self._cola.put({"tipo": "progreso", "pct": pct, "idx": idx, "texto": snippet[:60]})
            except Exception:
                pass

        try:
            resultado = transcribir(self._audio_path, on_progress=on_progress, modelo=modelo_elegido)
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

    # ---------------------------------------------------- Visualizador VU
    def _actualizar_medidor_audio(self):
        """Lee RMS thread-safe cada 100ms y actualiza Canvas VU con color semaforo."""
        if self._recorder.active:
            vol = float(self._recorder.current_volume)  # 0..100
            # Geometria canvas (puede ser 1 al inicio antes de render)
            try:
                w = self._canvas_meter.winfo_width()
                if w < 10:
                    w = 240
                h = 20
                fill_w = int(w * vol / 100.0)
                # Actualizar barra
                self._canvas_meter.coords(self._meter_bar, 0, 0, fill_w, h)
                # Color semaforo
                if vol > 92:
                    color = "#d32f2f"  # rojo saturacion
                    txt = "¡SATURADO!"
                    txt_color = "white"
                elif vol > 70:
                    color = "#f57c00"  # naranja alto
                    txt = "Alto"
                    txt_color = "white"
                elif vol > 30:
                    color = "#388e3c"  # verde optimo
                    txt = "Óptimo"
                    txt_color = "white"
                elif vol > 5:
                    color = "#66bb6a"  # verde bajo
                    txt = "Bajo"
                    txt_color = "black"
                else:
                    color = "#bdbdbd"  # gris silencio
                    txt = "Silencio"
                    txt_color = "#424242"
                self._canvas_meter.itemconfig(self._meter_bar, fill=color)
                self._canvas_meter.itemconfig(self._meter_text, text=txt, fill=txt_color)
                self.var_nivel.set(f"{int(vol)}%")
            except tk.TclError:
                pass
            # Re-programar mientras graba
            self.after(100, self._actualizar_medidor_audio)
        else:
            # Fuera de grabacion: reset
            try:
                self._canvas_meter.coords(self._meter_bar, 0, 0, 0, 20)
                self._canvas_meter.itemconfig(self._meter_bar, fill="#bdbdbd")
                self._canvas_meter.itemconfig(self._meter_text, text="En espera", fill="#424242")
                self.var_nivel.set("0%")
            except tk.TclError:
                pass

    # ---------------------------------------------------- Estado / cola / hilos
    def _set_ocupado(self, ocupado, accion=None):
        self._ocupado = ocupado
        if ocupado:
            if accion == "transcribir":
                # Determinate para transcripción con % real
                self.progreso.config(mode="determinate", maximum=100, value=0)
                self.var_progreso.set("0%")
            else:
                # Indeterminate para resumen/guardar
                self.progreso.config(mode="indeterminate")
                self.progreso.start(12)
                self.var_progreso.set("")
            # Texto muy visible segun accion
            texto = _ACCIONES.get(accion, "Trabajando...")
            self.var_estado.set(texto)
            self.lbl_estado.config(foreground="#e65100" if accion == "transcribir" else "#1565c0")
        else:
            self.progreso.stop()
            # No resetear a 0 si ya está completa (100%) para mostrar completado
            if self.progreso.cget("mode") == "indeterminate":
                self.progreso.config(mode="determinate", value=0)
                self.var_progreso.set("")
            self.lbl_estado.config(foreground="#2e7d32" if self._transcripcion else "#1565c0")

        # Deshabilitar campos para evitar cambios accidentales en proceso de 2h (requisito 4)
        estado_entry = "disabled" if ocupado else "normal"
        combo_state = "disabled" if ocupado else "readonly"
        for w in (self.entry_curso, self.entry_sesion, self.entry_titulo):
            try:
                w.config(state=estado_entry)
            except tk.TclError:
                pass
        try:
            self.combo_modelo.config(state=combo_state)
        except tk.TclError:
            pass
        # Botones relacionados a pipeline deshabilitados durante ocupado para evitar doble disparo
        if ocupado:
            self.btn_transcribir.config(state="disabled")
            self.btn_resumir.config(state="disabled")
            self.btn_guardar.config(state="disabled")
            self.btn_grabar.config(state="disabled")
            if accion == "transcribir":
                self.btn_cancelar.config(state="normal")
            else:
                self.btn_cancelar.config(state="disabled")
        else:
            self.btn_transcribir.config(state="normal")
            self.btn_resumir.config(state="normal")
            self.btn_guardar.config(state="normal")
            self.btn_grabar.config(state="normal")
            self.btn_cancelar.config(state="disabled")

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
        if tipo == "progreso":
            pct = int(mensaje.get("pct", 0))
            # Actualiza barra determinate
            try:
                self.progreso.config(value=pct)
                self.var_progreso.set(f"{pct}%")
                # Opcional: muestra snippet en estado sin saturar
                # self.var_estado.set(f"Transcribiendo... {pct}%")
            except tk.TclError:
                pass
            return
        if tipo == "transcripcion":
            if mensaje["ok"]:
                datos = mensaje["datos"]
                self._transcripcion = datos["texto"]
                self.texto.delete("1.0", "end")
                self.texto.insert("1.0", self._transcripcion)
                # Barra a 100%
                try:
                    self.progreso.config(value=100)
                    self.var_progreso.set("100%")
                except tk.TclError:
                    pass
                # Requisito 3: texto exacto al completar
                self.var_estado.set("Transcripción completada")
                self.lbl_estado.config(foreground="#2e7d32")
                rtf = datos.get("rtf")
                tiempo = datos.get("tiempo_transcripcion")
                modelo = datos.get("modelo", "?")
                batched = "⚡batched" if datos.get("batched") else "estándar"
                self._log(f"[{self._hora()}] Transcripción completada ({datos['duracion_audio']}s, modelo={modelo}, {batched}, {tiempo}s, RTF={rtf}).")
                self._set_ocupado(False)
                # Pipeline automatico a resumen si checkbox activo
                if self.var_auto_resumen.get():
                    self._log(f"[{self._hora()}] Pipeline automático: generando resumen...")
                    self.var_estado.set("Transcripción completada. Generando resumen automático...")
                    # Delay para que UI muestre estado antes de hilo
                    self.after(600, self._iniciar_resumen)
                else:
                    self.var_estado.set("Transcripción completada. Pulsa 'Generar resumen' para continuar.")
            else:
                self.var_estado.set("Error en la transcripción.")
                self.lbl_estado.config(foreground="#c62828")
                # Mensaje cancelación es esperado, no crítico
                if "cancelada" in mensaje["error"].lower():
                    self._log(f"[{self._hora()}] Transcripción cancelada.")
                    self.var_estado.set("Transcripción cancelada.")
                    self.lbl_estado.config(foreground="#616161")
                    self.progreso.config(value=0)
                    self.var_progreso.set("")
                else:
                    messagebox.showerror("Transcripción", mensaje["error"])
                    self._log(f"[{self._hora()}] ERROR transcripción: {mensaje['error']}")
                self._set_ocupado(False)

        elif tipo == "resumen":
            if mensaje["ok"]:
                self._resumen = mensaje["texto"]
                self.var_estado.set("Resumen generado. Revisa el texto y guarda la nota.")
                self.lbl_estado.config(foreground="#2e7d32")
                self._log(f"[{self._hora()}] Resumen generado por opencode.")
            else:
                self.var_estado.set("Error al generar el resumen.")
                self.lbl_estado.config(foreground="#c62828")
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
