import base64
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error, request
from http.server import ThreadingHTTPServer
import gemini_sekil as images
import ortak
import sunucu

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=')
SPEC = {'kanji':'日','partiya':1,'image_prompt':'A clay sun inside a square frame.','negative_prompt':'letters'}


class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.files = patch.object(ortak, 'CIKTI_DIZINI', self.temp.name)
        self.files.start(); self.addCleanup(self.files.stop)
        self.env = patch.dict('os.environ', {'GEMINI_API_KEY':'test-key-never-sent'})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_no_key_blocks_generation_without_network(self):
        with patch.dict('os.environ', {'GEMINI_API_KEY':''}), patch.object(images, 'generate') as call:
            with self.assertRaises(images.ImageError) as e:
                images.start(SPEC)
            self.assertEqual(e.exception.code, 409)
            call.assert_not_called()

    def test_request_contract_and_credentials_only_in_header(self):
        payload = {'steps':[{'type':'model_output','content':[{'type':'image','mime_type':'image/png','data':base64.b64encode(PNG).decode()}]}]}
        with patch.object(images.request, 'build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(json.dumps(payload).encode())
            binary, mime, ext = images.generate('A sun', 'gemini-nano-banana-2.1')
            req = opener.return_value.open.call_args.args[0]
            body = json.loads(req.data)
            self.assertEqual(req.full_url, images.ENDPOINT)
            self.assertEqual(req.get_header('X-goog-api-key'), 'test-key-never-sent')
            self.assertNotIn('test-key-never-sent', req.full_url + req.data.decode())
            self.assertEqual(body['response_format']['image_size'], '1K')
            self.assertEqual((binary,mime,ext), (PNG,'image/png','.png'))

    def test_provider_errors_do_not_expose_response_or_key(self):
        for status in (401, 403, 429, 500):
            with self.subTest(status=status), patch.object(images.request, 'build_opener') as opener:
                opener.return_value.open.side_effect = error.HTTPError(images.ENDPOINT, status, 'test-key-never-sent', {}, io.BytesIO(b'sensitive'))
                with self.assertRaises(images.ImageError) as e:
                    images.generate('A sun', 'model')
                self.assertNotIn('test-key-never-sent', str(e.exception))
                self.assertNotIn('sensitive', str(e.exception))
                self.assertEqual(opener.return_value.open.call_count, 1)

    def test_no_image_is_not_marked_success(self):
        with patch.object(images.request, 'build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(b'{"steps": []}')
            with self.assertRaises(images.ImageError):
                images.generate('A sun', 'model')

    def test_generation_cache_and_metadata(self):
        with patch.object(images, 'generate', return_value=(PNG, 'image/png', '.png')) as generate:
            job = images.start(SPEC)
            deadline = time.monotonic() + 3
            while job['id'] in images.ACTIVE and time.monotonic() < deadline:
                time.sleep(.01)
            saved = images.read(job['id'])
            self.assertEqual(saved['status'], 'completed')
            self.assertEqual(images.image_path(job['id']).read_bytes(), PNG)
            again = images.start(SPEC)
            self.assertEqual(again['id'], job['id'])
            self.assertEqual(generate.call_count, 1)
            self.assertNotIn('test-key-never-sent', json.dumps(saved))

    def test_duplicate_requests_share_running_job(self):
        with patch.object(images.threading, 'Thread') as thread:
            job = images.start(SPEC)
            try:
                self.assertEqual(images.start(SPEC)['id'], job['id'])
                self.assertEqual(thread.call_count, 1)
                with self.assertRaises(images.ImageError):
                    images.start({**SPEC, 'kanji':'月'})
            finally:
                images.ACTIVE.discard(job['id'])
            self.assertEqual(images.read(job['id'])['status'], 'interrupted')

    def test_brief_parser_and_validation(self):
        folder = Path(self.temp.name) / 'sekil'; folder.mkdir()
        (folder / 'run-b001-sekil.md').write_text('```json\n'+json.dumps([SPEC])+'\n```', encoding='utf-8')
        (folder / 'run-b002-sekil.md').write_text('```json\n'+json.dumps([{**SPEC,'kanji':'月'}])+'\n```', encoding='utf-8')
        self.assertEqual(images.briefs(1)[0]['kanji'], '日')
        for spec in ({**SPEC, 'kanji':'../'}, {**SPEC,'partiya':True}, {**SPEC,'image_prompt':None}):
            with self.assertRaises(images.ImageError):
                images.validate(spec)
        with self.assertRaises(images.ImageError):
            images.image_path('../secret')

    def test_http_cross_origin_and_stale_batch_rejected(self):
        with patch.object(sunucu.kanji_is_axini, 'status', return_value={'partiya':1,'kanjiler':[{'kanji':'日'}]}), patch.object(images, 'start') as generate:
            server = ThreadingHTTPServer(('127.0.0.1',0), sunucu.Isleyici)
            thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            url = f'http://127.0.0.1:{server.server_port}/api/gemini'
            try:
                for origin, spec, expected in [('http://localhost:9999', SPEC, 403), (None, {**SPEC,'partiya':2},409)]:
                    headers={'Content-Type':'application/json'}
                    if origin: headers['Origin']=origin
                    req=request.Request(url,data=json.dumps(spec).encode(),headers=headers)
                    with self.assertRaises(error.HTTPError) as e:
                        request.urlopen(req)
                    self.assertEqual(e.exception.code, expected)
                generate.assert_not_called()
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_claude_subprocess_environment_excludes_image_key(self):
        self.assertNotIn('GEMINI_API_KEY', ortak.ajan_ortami())


if __name__ == '__main__':
    unittest.main()
