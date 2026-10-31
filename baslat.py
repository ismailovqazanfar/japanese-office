"""Start the office with session-only image credentials. No key file is written.
Pulsuz yol: Cloudflare Workers AI (gündəlik pulsuz kvota). Açar verməsən açarsız Pollinations işləyir."""
import getpass
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path


def gizli(sual):
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        return getpass.getpass(sual).strip()


def main():
    root = Path(__file__).resolve().parent
    if not (root / 'ajanlar.json').exists():
        shutil.copyfile(root / 'ajanlar.example.json', root / 'ajanlar.json')
    env = dict(os.environ)
    try:
        if not (env.get('CF_ACCOUNT_ID') and env.get('CF_API_TOKEN')) and not env.get('GEMINI_API_KEY'):
            print('Şəkil üçün pulsuz Cloudflare Workers AI (README: "Pulsuz şəkil"). Boş buraxsan açarsız Pollinations işləyir.')
            acc = input('Cloudflare Account ID (boş = keç): ').strip()
            if acc:
                tok = gizli('Cloudflare API token (gizli): ')
                if tok:
                    env['CF_ACCOUNT_ID'], env['CF_API_TOKEN'] = acc, tok
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        print('\nGizli giriş mümkün olmadı. Adi terminalda yenidən başlat.')
        return 1
    print('Şəkil sorğusu yalnız "Şəkil yarat" düyməsi ilə göndərilir.')
    return subprocess.call([sys.executable, str(root / 'sunucu.py')], cwd=root, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
