"""Server-side Gemini image generation. Keys never enter jobs, responses or logs.
API contract: https://ai.google.dev/gemini-api/docs/image-generation (Interactions).
"""
import base64
import binascii
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from urllib import request, error
import ortak

ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/interactions'
MAX_RESPONSE = 28 * 1024 * 1024
LOCK = threading.Lock()
ACTIVE = set()


class ImageError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def config():
    return {'configured': bool(os.environ.get('GEMINI_API_KEY', '').strip()),
            'model': os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-nano-banana-2.1'),
            'busy': bool(ACTIVE)}


def directory():
    return Path(ortak.CIKTI_DIZINI) / 'sekiller'


def validate(data):
    if not isinstance(data, dict):
        raise ImageError(400, 'Şəkil məlumatı obyekt olmalıdır')
    kanji, prompt = data.get('kanji'), data.get('image_prompt')
    negative = data.get('negative_prompt', '')
    batch = data.get('partiya')
    if not isinstance(kanji, str) or not re.fullmatch(r'[\u3400-\u4dbf\u4e00-\u9fff]', kanji):
        raise ImageError(400, 'Bir kanji seç')
    if not isinstance(prompt, str) or not 10 <= len(prompt.strip()) <= 6000:
        raise ImageError(400, 'Şəkil promptu 10–6000 simvol olmalıdır')
    if not isinstance(negative, str) or len(negative) > 1000:
        raise ImageError(400, 'Mənfi prompt ən çox 1000 simvol ola bilər')
    if type(batch) is not int or not 1 <= batch <= 10000:
        raise ImageError(400, 'Yanlış qrup nömrəsi')
    return {'kanji': kanji, 'image_prompt': prompt.strip(), 'negative_prompt': negative.strip(), 'partiya': batch}


def job_id(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def save(job):
    directory().mkdir(parents=True, exist_ok=True)
    dest = directory() / (job['id'] + '.json')
    temp = dest.with_suffix('.tmp')
    temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(dest)


def read(job):
    if not isinstance(job, str) or not re.fullmatch(r'[a-f0-9]{64}', job):
        raise ImageError(400, 'Yanlış şəkil identifikatoru')
    try:
        data = json.loads((directory() / (job + '.json')).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ImageError(404, 'Şəkil işi tapılmadı') from None
    if data.get('status') == 'running' and job not in ACTIVE:
        data.update(status='interrupted', error='Server yenidən başladı. Yenidən sorğu göndərmək əlavə istifadə yarada bilər.')
    return data


def start(data):
    spec = validate(data)
    cfg = config()
    spec['model'] = cfg['model']
    identity = job_id(spec)
    with LOCK:
        try:
            existing = read(identity)
        except ImageError:
            existing = None
        if existing and existing.get('status') == 'completed':
            try:
                image_path(identity)
                return existing  # A repeated click never regenerates a completed image.
            except ImageError:
                raise ImageError(409, 'Əvvəlki şəkil faylı silinib. Yeni variant üçün promptu dəyiş.') from None
        if identity in ACTIVE:
            return read(identity)
        if ACTIVE:
            raise ImageError(409, 'Bir şəkil hazırlanır. Bitməsini gözlə.')
        if not cfg['configured']:
            raise ImageError(409, 'GEMINI_API_KEY yoxdur. Ofisi py baslat.py ilə başlat.')
        job = {**spec, 'id': identity, 'status': 'running'}
        save(job)
        ACTIVE.add(identity)
        try:
            threading.Thread(target=work, args=(job,), daemon=True).start()
        except Exception:
            ACTIVE.discard(identity)
            job.update(status='failed', error='Şəkil işi başlamadı.')
            save(job)
            raise ImageError(500, 'Şəkil işi başlamadı.') from None
        return dict(job)


def generate(prompt, model):
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    body = {'model': model, 'input': [{'type': 'text', 'text': prompt}],
            'response_format': {'type': 'image', 'aspect_ratio': '1:1', 'image_size': '1K'}}
    req = request.Request(ENDPOINT, data=json.dumps(body).encode(), method='POST',
                          headers={'Content-Type': 'application/json', 'x-goog-api-key': key})
    # Do not follow redirects carrying the credential header to another host.
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    try:
        with request.build_opener(NoRedirect).open(req, timeout=180) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ImageError(502, 'Şəkil cavabı çox böyükdür.')
        payload = json.loads(raw)
    except error.HTTPError as exc:
        messages = {400: 'Gemini model və ya sorğu ayarlarını qəbul etmədi.',
                    401: 'Gemini açarı qəbul olunmadı.',
                    403: 'Açarın icazəsini və layihənin API əlçatanlığını yoxla.',
                    404: 'Seçilən Gemini şəkil modeli əlçatan deyil.',
                    429: 'Gemini kvota limiti dolub. AI Studio-da kvota və ödəniş vəziyyətini yoxla.'}
        raise ImageError(502, messages.get(exc.code, 'Gemini sorğusu uğursuz oldu.')) from None
    except (error.URLError, TimeoutError, OSError):
        raise ImageError(502, 'Gemini bağlantısı kəsildi və ya vaxtı bitdi. Avtomatik təkrar sorğu göndərilmədi.') from None
    except ValueError:
        raise ImageError(502, 'Gemini cavabı oxunmadı.') from None
    if not isinstance(payload, dict):
        raise ImageError(502, 'Gemini cavabı oxunmadı.')
    parts = [payload.get('output_image')]
    for step in payload.get('steps', []):
        if isinstance(step, dict) and step.get('type') == 'model_output':
            parts.extend(step.get('content') or [])
    for part in parts:
        if not isinstance(part, dict) or part.get('type', 'image') != 'image' or not part.get('data'):
            continue
        try:
            binary = base64.b64decode(part['data'], validate=True)
        except (ValueError, TypeError, binascii.Error):
            continue
        mime = part.get('mime_type', 'image/png')
        signatures = {'image/png': (b'\x89PNG\r\n\x1a\n', '.png'), 'image/jpeg': (b'\xff\xd8\xff', '.jpg')}
        if mime in signatures and binary.startswith(signatures[mime][0]) and len(binary) <= 20*1024*1024:
            return binary, mime, signatures[mime][1]
        if mime == 'image/webp' and binary.startswith(b'RIFF') and binary[8:12] == b'WEBP':
            return binary, mime, '.webp'
    raise ImageError(502, 'Gemini şəkil qaytarmadı. Promptu və modelin cavab məhdudiyyətlərini yoxla.')


def work(job):
    try:
        prompt = job['image_prompt']
        if job['negative_prompt']:
            prompt += '\nAvoid: ' + job['negative_prompt']
        binary, mime, extension = generate(prompt, job['model'])
        target = directory() / (job['id'] + extension)
        temp = target.with_suffix(extension + '.tmp')
        temp.write_bytes(binary)
        temp.replace(target)
        job.update(status='completed', mime_type=mime, extension=extension,
                   image_url='/api/gemini/file/' + job['id'])
    except ImageError as exc:
        job.update(status='failed', error=str(exc))
    except Exception:
        # Never expose exception text: provider responses or credentials could be present.
        job.update(status='failed', error='Şəkil saxlanmadı və ya gözlənilməz xəta baş verdi.')
    finally:
        try:
            save(job)
        finally:
            ACTIVE.discard(job['id'])


def image_path(identity):
    job = read(identity)
    ext = job.get('extension')
    if ext not in ('.png', '.jpg', '.webp'):
        raise ImageError(404, 'Hazır şəkil yoxdur')
    path = directory() / (identity + ext)
    if path.is_symlink() or not path.is_file():
        raise ImageError(404, 'Hazır şəkil yoxdur')
    return path


def briefs(batch):
    """Read only generated image briefs for this batch; tolerate partial/malformed agent output."""
    result = {}
    folder = Path(ortak.CIKTI_DIZINI) / 'sekil'
    files = sorted(folder.glob(f'*-b{batch:03d}-*.md'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
    for path in files:
        if path.is_symlink() or path.stat().st_size > 200_000:
            continue
        text = path.read_text(encoding='utf-8')
        for block in re.findall(r'```json\s*(.*?)```', text, re.S):
            try:
                value = json.loads(block)
            except ValueError:
                continue
            if isinstance(value, dict) and 'kanji' in value:
                rows = [value]
            elif isinstance(value, dict):
                rows = [{**v, 'kanji': k} for k, v in value.items() if isinstance(v, dict)]
            else:
                rows = value if isinstance(value, list) else []
            for row in rows:
                try:
                    spec = validate({**row, 'partiya': batch})
                except (ImageError, TypeError):
                    continue
                result.setdefault(spec['kanji'], spec)
    return list(result.values())[:5]
