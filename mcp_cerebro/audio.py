import os
import time
import wave
import threading

import numpy as np
import sounddevice as sd

from . import config


class Recorder:
    """
    Recorder optimizado para grabaciones largas (hasta 2h continuas).

    Antes: acumulaba todos los frames float32 en self._frames (lista Python) ->
           ~ 440 MB raw + overhead lista ~500 MB para 2h -> riesgo desbordamiento.

    Ahora: modo streaming por defecto escribe directamente a WAV en disco
           por bloques usando wave, sin retener audio en RAM. Mantiene
           compatibilidad legacy (start() sin path -> buffer en RAM).
    - Calcula RMS por bloque y expone self.current_volume (0-100) thread-safe
      para visualizador VU en la GUI.
    """

    def __init__(self):
        self._stream = None
        self._wav = None
        self._wav_path = None
        self._use_streaming = False
        self._frames = []  # solo modo legacy
        self._samples_written = 0
        self.start_time = None
        self.active = False
        self._lock = threading.Lock()
        self._volume = 0.0  # 0..100

    @property
    def current_volume(self) -> float:
        """Nivel RMS actual 0-100, thread-safe para lectura desde UI."""
        with self._lock:
            return self._volume

    def _callback(self, indata, frames, time_info, status):
        # --- 1) Calculo RMS (Root Mean Square) para VU ---
        try:
            if indata.size > 0:
                # indata: np.float32 [-1,1] shape (frames, 1)
                # rms ~0.005 silencio, 0.05 voz normal, 0.2 voz fuerte
                rms = float(np.sqrt(np.mean(np.square(indata, dtype=np.float64))))
                # Escala perceptual a 0-100: rms*400 calibrado empiricamente
                # 0.01->4, 0.05->20, 0.1->40, 0.2->80, 0.25->100 (clip)
                vol = float(np.clip(rms * 400.0, 0, 100))
                with self._lock:
                    self._volume = vol
            else:
                with self._lock:
                    self._volume = 0.0
        except Exception:
            pass

        # --- 2) Escritura segun modo ---
        if self._use_streaming:
            if self._wav is not None:
                try:
                    # float32 -> int16 PCM
                    pcm = np.int16(np.clip(indata, -1.0, 1.0) * 32767)
                    # wave es thread-safe si protegemos con lock (callback en hilo audio)
                    with self._lock:
                        # pcm puede ser (N,1) -> bytes contiene intercalado correcto para mono
                        self._wav.writeframes(pcm.tobytes())
                        self._samples_written += pcm.shape[0]
                except Exception:
                    pass
        else:
            # Legacy: buffer en RAM (para server.py sin path / compatibilidad)
            try:
                self._frames.append(indata.copy())
                self._samples_written += indata.shape[0]
            except Exception:
                pass

    def start(self, path: str | None = None):
        """
        Inicia grabacion.
        :param path: Si se provee, activa modo streaming y escribe directo a ese WAV.
                     Si es None, usa modo legacy en RAM (compat con mcp_cerebro/server.py).
        """
        if self.active:
            raise RuntimeError("Ya hay una grabaci\u00f3n en curso. Det\u00e9n la grabaci\u00f3n anterior antes de iniciar otra.")

        self._samples_written = 0
        with self._lock:
            self._volume = 0.0
        self._wav_path = None
        self._wav = None

        if path:
            config.ensure_temp_dir()
            # asegurar carpeta destino existe
            dirpath = os.path.dirname(os.path.abspath(path))
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            self._wav_path = path
            self._wav = wave.open(path, "wb")
            self._wav.setnchannels(1)
            self._wav.setsampwidth(2)  # int16
            self._wav.setframerate(config.SAMPLE_RATE)
            self._use_streaming = True
            self._frames = None
        else:
            self._use_streaming = False
            self._frames = []

        try:
            self._stream = sd.InputStream(
                samplerate=config.SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()
        except sd.PortAudioError as exc:
            if self._wav is not None:
                try:
                    self._wav.close()
                except Exception:
                    pass
                self._wav = None
            raise RuntimeError(
                f"No se pudo acceder al micr\u00f3fono: {exc}. Verifica que el dispositivo est\u00e9 conectado y no est\u00e9 ocupado por otra aplicaci\u00f3n."
            ) from exc

        self.start_time = time.time()
        self.active = True

    def stop(self):
        """
        Detiene grabacion.
        Retorna:
          - Modo streaming (start(path)): (None, duracion_seg) -> archivo ya en disco en path provisto.
          - Modo legacy (start()): (audio_ndarray, duracion_seg) -> requiere save_wav().
        Duracion es precisa por muestras escritas, no solo wall-clock.
        """
        if not self.active or self._stream is None:
            raise RuntimeError("No hay una grabaci\u00f3n activa.")

        self._stream.stop()
        self._stream.close()
        self._stream = None
        wall_duration = time.time() - self.start_time
        accurate_duration = (
            self._samples_written / config.SAMPLE_RATE
            if self._samples_written > 0
            else wall_duration
        )
        self.active = False
        with self._lock:
            self._volume = 0.0

        if self._use_streaming:
            if self._wav is not None:
                try:
                    self._wav.close()
                except Exception:
                    pass
                self._wav = None
            path = self._wav_path
            self._wav_path = None
            self._use_streaming = False
            # Archivo ya persistido; caller conoce path (self._audio_path en app.py)
            return None, accurate_duration
        else:
            # Legacy: concatenar frames
            if self._frames:
                audio = np.concatenate(self._frames, axis=0).flatten()
            else:
                audio = np.array([], dtype=np.float32)
            self._frames = []
            return audio, accurate_duration

    def save_wav(self, audio, path):
        """
        Guarda ndarray float32 [-1,1] a WAV int16.
        Compat: si audio is None (ya en modo streaming), simplemente valida path existente.
        """
        if audio is None:
            # Streaming ya guardo el archivo
            if path and os.path.exists(path):
                return path
            if self._wav_path and os.path.exists(self._wav_path):
                return self._wav_path
            raise ValueError("No hay audio en memoria y no se encontr\u00f3 archivo streaming en disco.")

        from scipy.io import wavfile

        pcm = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
        wavfile.write(path, config.SAMPLE_RATE, pcm)
        return path
