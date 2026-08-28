"""
Benchmark offline rápido para mcp-cerebro
Mide RTF (realtime factor) y tiempo por modelo/beam/batched sin necesidad de internet
si los modelos ya están descargados. Genera audio sintético si no se provee --audio.

Uso:
  python scripts/bench_transcripcion.py --audio temporal/mi_clase.wav --modelos tiny,small,distil-small --beam 1 --batched 1
  python scripts/bench_transcripcion.py --duracion 30 --modelos small --beam 1,5 --batched 0,1
"""
import argparse
import os
import sys
import time
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from mcp_cerebro import config


def generar_audio_sintetico(path: str, duracion_seg: int = 30, sr: int = 16000):
    """Genera WAV sintético con tonos + silencios (ejercita VAD y modelo)."""
    # 16kHz mono, mezcla de senos + envolvente de voz simulada (no es voz real, pero el modelo corre)
    t = np.arange(int(sr * duracion_seg), dtype=np.float32) / sr
    # Señal base: 220Hz + 440Hz modulada para no ser silencio puro (VAD la mantiene)
    envolvente = 0.5 + 0.5 * np.sin(2 * np.pi * 2.0 * t)  # 2Hz modulación
    # Pausas cada 5s (1s silencio) para probar VAD
    pausa = (t % 5) < 4
    señal = (0.3 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 440 * t)) * envolvente * pausa
    # Añade ruido suave
    señal += 0.02 * np.random.randn(*señal.shape).astype(np.float32)
    señal = np.clip(señal, -1.0, 1.0)
    pcm = np.int16(señal * 32767)
    wavfile.write(path, sr, pcm)
    return path


def bench_one(audio_path: str, modelo: str, beam: int, batched: bool):
    # Override config en caliente (afecta _get_model cache key)
    orig_model = config.WHISPER_MODEL
    orig_beam = config.WHISPER_BEAM_SIZE
    orig_batched = config.WHISPER_BATCHED
    try:
        config.WHISPER_MODEL = modelo
        config.WHISPER_BEAM_SIZE = beam
        config.WHISPER_BATCHED = batched
        # Invalidar cache para forzar modelo distinto si es necesario no es obligatorio,
        # _get_model usa cache key, así que basta cambiar config
        from mcp_cerebro import transcripcion
        # Limpiar cancel flag
        transcripcion.limpiar_cancelacion()
        t0 = time.time()
        prog_updates = []

        def on_prog(idx, end, total, snippet):
            prog_updates.append((idx, end, total))

        res = transcripcion.transcribir(audio_path, on_progress=on_prog, modelo=modelo, beam_size=beam, use_batched=batched)
        elapsed = time.time() - t0
        dur = res.get("duracion_audio", 0) or 1
        rtf = elapsed / dur if dur else None
        return {
            "ok": True,
            "modelo": res.get("modelo"),
            "beam": res.get("beam_size"),
            "batched": res.get("batched"),
            "duracion_audio": dur,
            "tiempo": round(elapsed, 2),
            "rtf": round(rtf, 3) if rtf else None,
            "segmentos": len(res.get("segmentos", [])),
            "progress_calls": len(prog_updates),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:600], "modelo": modelo, "beam": beam, "batched": batched}
    finally:
        config.WHISPER_MODEL = orig_model
        config.WHISPER_BEAM_SIZE = orig_beam
        config.WHISPER_BATCHED = orig_batched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", type=str, default=None, help="Ruta WAV real. Si no se da, genera sintético")
    ap.add_argument("--duracion", type=int, default=30, help="Duración sintética si --audio no se da")
    ap.add_argument("--modelos", type=str, default="tiny,small,distil-small", help="Lista coma: tiny,base,small,medium,distil-small,distil-large-v3,large-v3-turbo")
    ap.add_argument("--beam", type=str, default="1", help="Lista coma: 1,5")
    ap.add_argument("--batched", type=str, default="1,0", help="Lista coma: 1,0")
    ap.add_argument("--repetir", type=int, default=1, help="Repeticiones por combinación")
    args = ap.parse_args()

    modelos = [m.strip() for m in args.modelos.split(",") if m.strip()]
    beams = [int(b.strip()) for b in args.beam.split(",") if b.strip()]
    batcheds = [bool(int(b.strip())) if b.strip() in ("0", "1") else b.strip().lower() in ("true", "yes", "1") for b in args.batched.split(",")]

    if args.audio:
        audio_path = args.audio
        if not os.path.exists(audio_path):
            print(f"ERROR: no existe --audio {audio_path}")
            sys.exit(2)
        tmp_path = None
        print(f"[bench] Usando audio real: {audio_path}")
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=str(PROJECT_DIR / "temporal"))
        tmp_path = tmp.name
        tmp.close()
        # Genera sintético
        generar_audio_sintetico(tmp_path, duracion_seg=args.duracion, sr=config.SAMPLE_RATE)
        audio_path = tmp_path
        print(f"[bench] Audio sintético generado: {audio_path} ({args.duracion}s, {config.SAMPLE_RATE}Hz)")

    # Warmup: listar descarga estado
    from mcp_cerebro.transcripcion import listar_modelos
    print(f"[bench] Modelos disponibles: {', '.join(listar_modelos()[:6])}...")
    print(f"[bench] Config base: compute={config.WHISPER_COMPUTE_TYPE}, cpu_threads={config.WHISPER_CPU_THREADS}, vad_silence={config.WHISPER_VAD_MIN_SILENCE_MS}ms")
    print("=" * 80)
    print(f"{'modelo':<18} {'beam':<5} {'batched':<8} {'tiempo(s)':<10} {'RTF':<7} {'segs':<5} {'ok'}")
    print("-" * 80)

    resultados = []
    for modelo in modelos:
        for beam in beams:
            for batched in batcheds:
                for rep in range(args.repetir):
                    sys.stdout.write(f"  -> {modelo} beam={beam} batched={batched} ... ")
                    sys.stdout.flush()
                    r = bench_one(audio_path, modelo, beam, batched)
                    resultados.append(r)
                    if r["ok"]:
                        print(f"OK  {r['tiempo']:>6}s  RTF={r['rtf']:<5}  segs={r['segmentos']}")
                    else:
                        print(f"FAIL {r['error'][:80]}")

    print("=" * 80)
    # Resumen sorted por RTF
    oks = [r for r in resultados if r["ok"]]
    if oks:
        oks_sorted = sorted(oks, key=lambda x: x["rtf"] if x["rtf"] else 999)
        print("Resumen (más rápido primero):")
        for r in oks_sorted:
            print(f"  {r['modelo']:<18} beam={r['beam']} batched={1 if r['batched'] else 0}  RTF={r['rtf']:<6}  {r['tiempo']}s")
        best = oks_sorted[0]
        print(f"\nRecomendación: {best['modelo']} beam={best['beam']} batched={best['batched']} (RTF={best['rtf']})")
        # Estimación para 60min
        est_60 = best["rtf"] * 3600 if best["rtf"] else None
        if est_60:
            print(f"Estimación 60min clase -> {est_60/60:.1f} min ({est_60:.0f}s) de transcripción")
    else:
        print("Sin resultados OK. Revisa modelos descargados.")

    if tmp_path and os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
            print(f"[bench] Temp eliminado: {tmp_path}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
