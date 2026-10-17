"""Two uploads -> existing Auralis job lifecycle -> matched WAV."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import tempfile
import threading

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..voice.reference_match import MAX_BYTES, match_vocal, validate_audio

router = APIRouter(prefix='/voice/match', tags=['voice'])
_busy = threading.Lock()


def _run(job_id, guide, take, strength):
    from .main import JOBS
    job = JOBS[job_id]
    try:
        result = match_vocal(guide, take, os.path.join(job['work'], 'auralis_matched_vocal.wav'),
            os.path.join(job['work'], 'vocal_match_report.json'), strength,
            progress=lambda stage, pct: job.update(stage=stage, pct=float(pct)))
        job.update(stage='done', pct=100.0, result=result)
    except ValueError as exc:
        job.update(stage='error', error=str(exc))
    except Exception:
        job.update(stage='error', error='Vocal matching failed. Try shorter, isolated vocal sections.')
    finally:
        _busy.release()


@router.post('')
async def create_match(guide: UploadFile = File(...), take: UploadFile = File(...),
                       melody_strength: float = Form(1.0, ge=0.0, le=1.0)):
    for upload in (guide, take):
        if Path(upload.filename or '').suffix.lower() != '.wav':
            raise HTTPException(415, 'Provide a demo vocal WAV and your own vocal WAV.')
    if not _busy.acquire(blocking=False):
        raise HTTPException(409, 'A vocal match is already running. Wait for it to finish.')
    queued = False
    try:
        with tempfile.TemporaryDirectory(prefix='auralis_match_upload_') as temporary:
            staged = []
            for label, upload in [('guide', guide), ('take', take)]:
                path = Path(temporary) / (label + '.wav')
                total = 0
                with path.open('wb') as destination:
                    while chunk := await upload.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise HTTPException(413, 'Each vocal WAV must be 100 MiB or smaller.')
                        destination.write(chunk)
                try:
                    validate_audio(path, 'Demo vocal' if label == 'guide' else 'Your vocal')
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from None
                staged.append(path)
            from .main import JOBS, _create_job
            job_id = _create_job()
            job = JOBS[job_id]
            job.update(kind='vocal-match', stage='queued', pct=0.0)
            paths = [str(Path(job['work']) / name) for name in ['guide.wav', 'take.wav']]
            for source, destination in zip(staged, paths):
                os.replace(source, destination)
            asyncio.create_task(asyncio.to_thread(_run, job_id, *paths, melody_strength))
            queued = True
            return {'job_id': job_id, 'status': 'started'}
    finally:
        if not queued:
            _busy.release()
        await guide.close()
        await take.close()


@router.get('/{job_id}/audio/{which}')
def match_audio(job_id: str, which: str):
    from .main import JOBS
    if which not in {'guide', 'take', 'result'}:
        raise HTTPException(404, 'Unknown vocal preview.')
    job = JOBS.get(job_id)
    if not job or job.get('kind') != 'vocal-match':
        raise HTTPException(404, 'Unknown vocal match.')
    if which == 'result' and (job.get('stage') != 'done' or not job.get('result')):
        raise HTTPException(409, 'Your matched vocal is not ready yet.')
    filename = 'auralis_matched_vocal.wav' if which == 'result' else which + '.wav'
    path = Path(job['work']) / filename
    if not path.is_file():
        raise HTTPException(410, 'This vocal file is no longer available.')
    return FileResponse(path, filename=filename, media_type='audio/wav')


@router.get('/{job_id}/report')
def match_report(job_id: str):
    from .main import JOBS
    job = JOBS.get(job_id)
    if not job or job.get('kind') != 'vocal-match' or job.get('stage') != 'done':
        raise HTTPException(404, 'No vocal match report is ready.')
    path = Path(job['work']) / 'vocal_match_report.json'
    if not path.is_file():
        raise HTTPException(410, 'This report is no longer available.')
    return FileResponse(path, filename='vocal_match_report.json', media_type='application/json')
