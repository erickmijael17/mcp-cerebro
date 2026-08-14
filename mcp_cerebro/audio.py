import time

import numpy as np
import sounddevice as sd

from . import config


class Recorder:
    def __init__(self):
        self._frames = []
        self._stream = None
        self.start_time = None
        self.active = False

    def _callback(self, indata, frames, time_info, status):
        self._frames.append(indata.copy())

    def start(self):
        if self.active:
            raise RuntimeError("Ya hay una grabación en curso. Detén la grabación anterior antes de iniciar otra.")

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
            raise RuntimeError(
                f"No se pudo acceder al micrófono: {exc}. Verifica que el dispositivo esté conectado y no esté ocupado por otra aplicación."
            ) from exc

        self.start_time = time.time()
        self.active = True

    def stop(self):
        if not self.active or self._stream is None:
            raise RuntimeError("No hay una grabación activa.")

        self._stream.stop()
        self._stream.close()
        self._stream = None
        duration = time.time() - self.start_time
        self.active = False

        audio = np.concatenate(self._frames, axis=0).flatten()
        return audio, duration

    def save_wav(self, audio, path):
        from scipy.io import wavfile

        pcm = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
        wavfile.write(path, config.SAMPLE_RATE, pcm)
        return path