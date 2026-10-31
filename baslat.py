"""Start the office with a masked, session-only Gemini credential. No key file is written."""
import getpass
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    if not (root / 'ajanlar.json').exists():
        shutil.copyfile(root / 'ajanlar.example.json', root / 'ajanlar.json')
    env = dict(os.environ)
    if not env.get('GEMINI_API_KEY'):
        print('Yeni Gemini açarını daxil et. Boş buraxsan ofis şəkil API-si olmadan açılacaq.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            try:
                key = getpass.getpass('Gemini API key (gizli): ').strip()
            except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
                print('\nGizli giriş mümkün olmadı. Adi terminalda yenidən başlat.')
                return 1
        if key:
            env['GEMINI_API_KEY'] = key
    print('Şəkil sorğusu yalnız Gemini ilə yarat düyməsi ilə göndərilir; API istifadəsi ödənişli ola bilər.')
    return subprocess.call([sys.executable, str(root / 'sunucu.py')], cwd=root, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
