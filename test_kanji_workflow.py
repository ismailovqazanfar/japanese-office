import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import kanji_is_axini as workflow
import ortak
import sunucu


class WorkflowTests(unittest.TestCase):
    def test_all_cards_are_included_and_batches_do_not_overlap(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ortak, 'DURUM_DIZINI', tmp):
            first = workflow.status()
            self.assertEqual(first['kanji_sayi'], 673)
            self.assertEqual(first['partiya_sayi'], 135)
            all_chars = []
            for i in range(1, first['partiya_sayi'] + 1):
                all_chars += [r['kanji'] for r in workflow.sec(i)['kanjiler']]
            self.assertEqual(len(all_chars), len(set(all_chars)))
            self.assertEqual(len(all_chars), 673)
            self.assertEqual(len(workflow.status()['kanjiler']), 3)

    def test_selection_validation_and_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ortak, 'DURUM_DIZINI', tmp):
            first = workflow.status()
            prompt = workflow.prompt_elave('test', first)
            workflow.sec(2)
            self.assertIn('b001', prompt)
            for invalid in (True, '2', 0, -1, 136, None):
                with self.assertRaises(ValueError):
                    workflow.sec(invalid)
            self.assertEqual(workflow.status()['partiya'], 2)

    def test_limit_matches_schema_and_prompt(self):
        table = {'a': {'id':'a','ad':'A','oda':'a','kurulu':True,'ne_zaman_metin':'','aciklama':''}}
        tasks = [{'ajan':'a','prompt':'test'}] * sunucu.MAKS_ATAMA
        self.assertEqual(len(sunucu.ceo_dogrula({'cevap':'ok','atamalar':tasks}, table, '')[1]), sunucu.MAKS_ATAMA)
        with self.assertRaises(ValueError):
            sunucu.ceo_dogrula({'cevap':'ok','atamalar':tasks + tasks[:1]}, table, '')
        self.assertIn(f'Ən çox {sunucu.MAKS_ATAMA}', sunucu.ceo_promptu('', table))
        self.assertEqual(sunucu.CEO_SEMASI['properties']['atamalar']['maxItems'], sunucu.MAKS_ATAMA)

    def test_http_selection_rejects_change_while_busy(self):
        import threading
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        with tempfile.TemporaryDirectory() as tmp, patch.object(ortak, 'DURUM_DIZINI', tmp), patch.object(ortak, 'ajanlari_yukle', return_value=({}, {'hekayeci': {}})):
            server = ThreadingHTTPServer(('127.0.0.1', 0), sunucu.Isleyici)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_port}/api/kanji'
            try:
                request = urllib.request.Request(url, data=b'{"partiya":2}', headers={'Content-Type':'application/json'})
                with patch.object(ortak, 'ajan_mesgul', return_value=True):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(request)
                    self.assertEqual(error.exception.code, 409)
                with patch.object(ortak, 'ajan_mesgul', return_value=False):
                    with urllib.request.urlopen(request) as response:
                        self.assertEqual(json.load(response)['partiya'], 2)
                with urllib.request.urlopen(url) as response:
                    self.assertEqual(json.load(response)['partiya'], 2)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_existing_configuration_preserves_personal_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'agents.json'
            config.write_text(json.dumps({'ajanlar':[{'id':'hekayeci','cwd':tmp,'oda':'yazi','model':'personal-model','izinli_araclar':['Read'],'hazir_gorevler':[]}]}))
            with patch.object(ortak, 'AJANLAR_DOSYASI', str(config)):
                _, table = ortak.ajanlari_yukle()
                self.assertEqual(table['hekayeci']['model'], 'personal-model')
                self.assertEqual(table['hekayeci']['cwd'], tmp)
                self.assertEqual(table['hekayeci']['izinli_araclar'], ['Read'])
                self.assertIn('sekil', table)
                self.assertTrue(table['hekayeci']['hazir_gorevler'][0]['etiket'].startswith('Aktiv '))
            self.assertNotIn('sekil', config.read_text())


if __name__ == '__main__':
    unittest.main()
