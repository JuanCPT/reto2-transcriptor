"""YT Transcriptor // Matrix Edition - web backend.

Optimizations:
- Reuses the loaded Whisper model between requests.
- Auto mode prefers CUDA/float16 when CTranslate2 can see a CUDA device;
  otherwise it uses CPU/int8 and a lighter base model.
- Falls back to CPU when CUDA model initialization fails.
- Runs transcriptions as background jobs and reports measured segment progress.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
import ctypes
import gc
import os
import time
import uuid

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.utils import secure_filename

try:
    import ctranslate2
except ImportError:  # faster-whisper normally installs it, but keep health endpoint informative.
    ctranslate2 = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
TRANSCRIPT_DIR = BASE_DIR / "transcripts"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".mp3", ".mp4", ".m4a", ".wav", ".webm", ".mkv", ".ogg",
    ".aac", ".flac", ".wma", ".3gp", ".mpeg", ".mpga", ".mov",
}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB
JOB_RETENTION_SECONDS = 60 * 60

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
CORS(app, resources={r"/api/*": {"origins": ["http://localhost", "http://127.0.0.1", "http://transcriptor.test"]}})

# Keep at most one model resident: better for PCs with limited RAM/VRAM.
_model = None
_model_key = None
_runtime_info: dict | None = None
_cuda_disabled_for_session = False
_cuda_runtime_check_cache: tuple[bool, str] | None = None
_cuda_dll_handles: list[object] = []
_model_lock = Lock()
_transcription_lock = Lock()
_jobs_lock = Lock()
_jobs: dict[str, dict] = {}


def _cuda_device_count() -> int:
    """Return the number of CUDA devices CTranslate2 can actually use."""
    if ctranslate2 is None:
        return 0
    try:
        return max(0, int(ctranslate2.get_cuda_device_count()))
    except Exception as exc:
        app.logger.info("CUDA no disponible para CTranslate2: %s", exc)
        return 0


def _cuda_runtime_check() -> tuple[bool, str]:
    """Check that the CUDA libraries required by the current CTranslate2 build can load.

    CTranslate2 may report a CUDA device even when the cuBLAS/cuDNN DLLs needed
    for actual inference are missing. On Windows, test them before choosing GPU.
    """
    global _cuda_runtime_check_cache
    if _cuda_runtime_check_cache is not None:
        return _cuda_runtime_check_cache

    if os.name != "nt":
        # On non-Windows systems, CTranslate2's CUDA device probe is the portable
        # preflight; inference-time failures are still handled by CPU fallback.
        _cuda_runtime_check_cache = (True, "")
        return _cuda_runtime_check_cache

    required_dlls = ("cublas64_12.dll", "cudnn64_9.dll")
    for dll_name in required_dlls:
        try:
            handle = ctypes.WinDLL(dll_name)
            # Keep handles alive for the server lifetime, preventing unload.
            _cuda_dll_handles.append(handle)
        except OSError as exc:
            _cuda_runtime_check_cache = (
                False,
                f"No se pudo cargar {dll_name}: {exc}",
            )
            return _cuda_runtime_check_cache

    _cuda_runtime_check_cache = (True, "")
    return _cuda_runtime_check_cache


def _is_cuda_runtime_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    markers = (
        "cublas", "cudnn", "cuda", "out of memory", "alloc_failed",
        "cannot be loaded", "could not be loaded", "failed to load",
    )
    return any(marker in message for marker in markers)


def _disable_cuda_for_session(reason: str) -> None:
    """Avoid repeated GPU failures after a CUDA runtime error; force future CPU attempts."""
    global _cuda_disabled_for_session, _model, _model_key, _runtime_info
    _cuda_disabled_for_session = True
    with _model_lock:
        if _model_key is not None and len(_model_key) >= 3 and _model_key[2] == "cuda":
            _model = None
            _model_key = None
            _runtime_info = None
    app.logger.warning("Se desactiva CUDA para esta sesión y se usará CPU: %s", reason)
    gc.collect()


def _cpu_threads() -> int:
    # Use several cores but leave room for Windows/UI and other tasks.
    return max(1, min(os.cpu_count() or 4, 8))


def _load_model(selection: str, model_name: str, device: str, compute_type: str):
    """Load/cache one model. Caller must hold _model_lock."""
    global _model, _model_key, _runtime_info
    key = (selection, model_name, device, compute_type)
    if _model is not None and _model_key == key:
        return _model, dict(_runtime_info or {})

    # Avoid keeping an old, differently sized model in memory when switching.
    _model = None
    _model_key = None
    _runtime_info = None
    gc.collect()

    kwargs = {"device": device, "compute_type": compute_type}
    if device == "cpu":
        kwargs["cpu_threads"] = _cpu_threads()

    loaded = WhisperModel(model_name, **kwargs)
    _model = loaded
    _model_key = key
    _runtime_info = {
        "selection": selection,
        "model": model_name,
        "device": device,
        "compute_type": compute_type,
        "cpu_threads": _cpu_threads() if device == "cpu" else None,
    }
    app.logger.info(
        "Modelo listo: %s en %s (%s)%s",
        model_name, device, compute_type,
        f", cpu_threads={_cpu_threads()}" if device == "cpu" else "",
    )
    return loaded, dict(_runtime_info)


def get_model(requested: str):
    """Select a sensible configuration and avoid CUDA when its runtime is incomplete."""
    global _cuda_disabled_for_session
    if WhisperModel is None:
        raise RuntimeError("faster-whisper no está instalado en este entorno de Python.")

    cuda_count = _cuda_device_count()
    runtime_ok, runtime_reason = _cuda_runtime_check() if cuda_count > 0 else (False, "CTranslate2 no detecta dispositivos CUDA.")
    can_use_cuda = cuda_count > 0 and runtime_ok and not _cuda_disabled_for_session

    if cuda_count > 0 and not runtime_ok:
        _cuda_disabled_for_session = True
        app.logger.warning("CUDA aparece visible, pero su runtime no está completo. Se usará CPU. Detalle: %s", runtime_reason)

    with _model_lock:
        if requested == "auto":
            # Base is practical on CPU-only/basic PCs; use small when GPU runtime works.
            if can_use_cuda:
                try:
                    return _load_model("auto", "small", "cuda", "float16")
                except Exception as exc:
                    _cuda_disabled_for_session = True
                    app.logger.warning(
                        "No se pudo iniciar Whisper en CUDA (%s). Se usará CPU con el modelo base y no se reintentará CUDA en esta sesión.", exc
                    )
            return _load_model("auto", "base", "cpu", "int8")

        # For manually selected models, prefer GPU only if both the device and runtime work.
        if can_use_cuda:
            try:
                return _load_model(requested, requested, "cuda", "float16")
            except Exception as exc:
                _cuda_disabled_for_session = True
                app.logger.warning(
                    "CUDA no pudo cargar el modelo %s (%s). Se intentará CPU/int8 y no se reintentará CUDA en esta sesión.", requested, exc
                )
        return _load_model(requested, requested, "cpu", "int8")


def format_time(seconds) -> str:
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def update_job(job_id: str, **changes) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(changes)
            job["updated_at"] = time.time()


def append_job_segment(job_id: str, line: str, segment_count: int, **changes) -> None:
    """Append one new segment without copying the transcript list on every iteration."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.setdefault("segments", []).append(line)
            job["segment_count"] = segment_count
            job.update(changes)
            job["updated_at"] = time.time()


def cleanup_old_jobs() -> None:
    cutoff = time.time() - JOB_RETENTION_SECONDS
    with _jobs_lock:
        for job_id, job in list(_jobs.items()):
            if job.get("created_at", time.time()) < cutoff and job.get("status") in {"done", "error"}:
                _jobs.pop(job_id, None)


def _transcribe_attempt(job_id: str, upload_path: Path, model, runtime: dict,
                        language: str | None) -> tuple[list[str], list[str], float, float, object]:
    """Run one complete transcription attempt; keep transcript segments local until success.

    Keeping partial segments out of the polling API makes a GPU-to-CPU retry safe:
    the UI will not display duplicate fragments from a failed GPU attempt.
    """
    beam_size = 1 if runtime["device"] == "cpu" else 5
    segments_iter, info = model.transcribe(
        str(upload_path), language=language, vad_filter=True, beam_size=beam_size
    )
    duration = float(getattr(info, "duration", 0) or 0)
    update_job(
        job_id,
        duration_seconds=duration,
        language=getattr(info, "language", None),
        progress=12,
        progress_indeterminate=True,
        note=f"Procesando audio con {runtime['model']} en {runtime['device']}.",
    )

    lines: list[str] = []
    text_parts: list[str] = []
    last_end = 0.0
    segment_count = 0
    for segment in segments_iter:
        segment_text = (segment.text or "").strip()
        if not segment_text:
            continue
        start = float(segment.start or 0)
        end = float(segment.end or start)
        last_end = max(last_end, end)
        lines.append(f"[{format_time(start)} → {format_time(end)}] {segment_text}")
        text_parts.append(segment_text)
        segment_count += 1

        if duration > 0:
            measured_progress = min(95, max(12, int(12 + (last_end / duration) * 82)))
            update_job(
                job_id,
                progress=measured_progress,
                progress_indeterminate=False,
                note=f"Transcribiendo: {format_time(last_end)} de {format_time(duration)} de audio procesados.",
                last_audio_second=last_end,
                segment_count=segment_count,
            )
        else:
            update_job(
                job_id,
                progress=12,
                progress_indeterminate=True,
                note=f"Transcribiendo; {segment_count} segmentos reconocidos.",
                last_audio_second=last_end,
                segment_count=segment_count,
            )

    if not text_parts:
        raise ValueError("Whisper no detectó palabras. Comprueba que el archivo contenga voz audible.")
    return lines, text_parts, last_end, duration, info


def run_transcription(job_id: str, upload_path: Path, original_name: str,
                      requested_model: str, language: str | None) -> None:
    try:
        update_job(
            job_id,
            status="loading_model",
            stage="loading_model",
            progress=8,
            progress_indeterminate=True,
            note="Cargando el modelo. La primera vez puede descargar archivos; las siguientes ejecuciones reutilizan la caché.",
        )

        # One active job and at most one model resident bounds RAM/VRAM on basic PCs.
        with _transcription_lock:
            model, runtime = get_model(requested_model)
            update_job(
                job_id,
                status="transcribing",
                stage="transcribing",
                progress=12,
                progress_indeterminate=True,
                note=f"Transcribiendo con {runtime['model']} en {runtime['device']} ({runtime['compute_type']}).",
                effective_model=runtime["model"],
                device=runtime["device"],
                compute_type=runtime["compute_type"],
            )

            try:
                lines, text_parts, last_end, duration, info = _transcribe_attempt(
                    job_id, upload_path, model, runtime, language
                )
            except Exception as exc:
                # CUDA may appear visible but fail only when the first GPU kernels run
                # (e.g. missing cublas64_12.dll). Retry the full file on CPU once.
                if runtime.get("device") != "cuda" or not _is_cuda_runtime_error(exc):
                    raise

                app.logger.exception("Falló la inferencia CUDA; se reintentará la transcripción en CPU")
                model = None
                _disable_cuda_for_session(str(exc))
                fallback_model, fallback_runtime = get_model(requested_model)
                update_job(
                    job_id,
                    status="transcribing",
                    stage="transcribing",
                    progress=8,
                    progress_indeterminate=True,
                    note=f"La GPU no pudo completar el trabajo; se reintenta desde el principio en CPU ({fallback_runtime['model']}, int8).",
                    effective_model=fallback_runtime["model"],
                    device=fallback_runtime["device"],
                    compute_type=fallback_runtime["compute_type"],
                    segment_count=0,
                )
                lines, text_parts, last_end, duration, info = _transcribe_attempt(
                    job_id, upload_path, fallback_model, fallback_runtime, language
                )
                runtime = fallback_runtime

        update_job(job_id, status="saving", stage="saving", progress=97,
                   progress_indeterminate=True, note="Guardando la transcripción en TXT…")
        full_text = "\n".join(lines)
        safe_stem = secure_filename(Path(original_name).stem) or "transcripcion"
        unique_id = uuid.uuid4().hex[:8]
        transcript_path = TRANSCRIPT_DIR / (
            f"{safe_stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{unique_id}.txt"
        )
        transcript_path.write_text(
            f"Archivo  : {original_name}\n"
            f"Duración : {format_time(last_end)}\n"
            f"Fecha    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            + "─" * 60 + "\n\n" + full_text,
            encoding="utf-8",
        )
        update_job(
            job_id,
            status="done",
            stage="done",
            progress=100,
            progress_indeterminate=False,
            note=f"Transcripción completada. Duración: {format_time(last_end)}.",
            transcript=full_text,
            duration=format_time(last_end),
            language=getattr(info, "language", None),
            saved_as=transcript_path.name,
            segment_count=len(lines),
            segments=lines,
            effective_model=runtime["model"],
            device=runtime["device"],
            compute_type=runtime["compute_type"],
        )
        app.logger.info(
            "Transcripción completada (%s, %s, %s): %s segmentos",
            runtime["model"], runtime["device"], runtime["compute_type"], len(lines)
        )
    except Exception as exc:
        app.logger.exception("Falló la transcripción del trabajo %s", job_id)
        update_job(job_id, status="error", stage="error", progress=0,
                   progress_indeterminate=False, note="La transcripción no se pudo completar.", error=str(exc))
    finally:
        try:
            upload_path.unlink(missing_ok=True)
        except OSError:
            app.logger.warning("No se pudo eliminar el archivo temporal: %s", upload_path)


@app.get("/api/health")
def health():
    cuda_count = _cuda_device_count()
    runtime_ok, runtime_reason = _cuda_runtime_check() if cuda_count > 0 else (False, "CTranslate2 no detecta dispositivos CUDA.")
    with _model_lock:
        runtime = dict(_runtime_info) if _runtime_info else None
        cuda_available = cuda_count > 0 and runtime_ok and not _cuda_disabled_for_session
    return jsonify({
        "ok": True,
        "service": "YT Transcriptor API",
        "whisper_available": WhisperModel is not None,
        "cuda_available": cuda_available,
        "cuda_device_count": cuda_count,
        "cuda_runtime_reason": runtime_reason if not cuda_available else "",
        "recommended_auto_model": "small" if cuda_available else "base",
        "runtime": runtime,
    })


@app.post("/api/transcribe")
def transcribe():
    if WhisperModel is None:
        return jsonify({"error": "No está instalada la dependencia faster-whisper en este entorno."}), 500

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Selecciona un archivo de audio o video."}), 400

    original_name = Path(uploaded.filename).name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Formato no admitido: {extension or '(sin extensión)'}."}), 415

    requested_model = request.form.get("model", "auto").strip()
    supported_models = {"auto", "tiny", "base", "small", "medium", "large-v3"}
    if requested_model not in supported_models:
        return jsonify({"error": "El modelo seleccionado no es válido."}), 400

    language = request.form.get("language", "es").strip()
    if language == "auto":
        language = None
    elif language not in {"es", "en", "pt", "fr"}:
        return jsonify({"error": "El idioma seleccionado no es válido."}), 400

    safe_name = secure_filename(original_name) or f"audio{extension}"
    job_id = uuid.uuid4().hex
    upload_path = UPLOAD_DIR / f"{job_id}_{safe_name}"

    try:
        uploaded.save(upload_path)
    except Exception as exc:
        app.logger.exception("No se pudo guardar la subida")
        return jsonify({"error": f"No se pudo guardar el archivo subido: {exc}"}), 500

    now = time.time()
    cleanup_old_jobs()
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "filename": original_name,
            "status": "queued",
            "stage": "queued",
            "progress": 3,
            "progress_indeterminate": False,
            "note": "Archivo recibido. Preparando el procesamiento…",
            "segments": [],
            "segment_count": 0,
            "created_at": now,
            "updated_at": now,
        }

    worker = Thread(
        target=run_transcription,
        args=(job_id, upload_path, original_name, requested_model, language),
        daemon=True,
        name=f"transcription-{job_id[:8]}",
    )
    worker.start()
    return jsonify({"ok": True, "job_id": job_id, "message": "Archivo recibido; el procesamiento comenzó."}), 202


@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    try:
        after = max(0, int(request.args.get("after", "0")))
    except ValueError:
        after = 0
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return jsonify({"error": "No se encontró el trabajo. Inicia de nuevo la transcripción."}), 404
        segments = job.get("segments", [])
        payload = {
            "ok": True,
            "job_id": job_id,
            "filename": job.get("filename"),
            "status": job.get("status"),
            "stage": job.get("stage"),
            "progress": job.get("progress"),
            "progress_indeterminate": job.get("progress_indeterminate", False),
            "note": job.get("note", ""),
            "segments": segments[after:],
            "segment_count": len(segments),
            "duration": job.get("duration"),
            "language": job.get("language"),
            "saved_as": job.get("saved_as"),
            "effective_model": job.get("effective_model"),
            "device": job.get("device"),
            "compute_type": job.get("compute_type"),
        }
        if job.get("status") == "done":
            payload["transcript"] = job.get("transcript", "")
        if job.get("status") == "error":
            payload["error"] = job.get("error", "Error desconocido durante la transcripción.")
        return jsonify(payload)


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": "El archivo supera el límite de 500 MB."}), 413


if __name__ == "__main__":
    # Apache serves the static frontend; Flask is a localhost-only API.
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
