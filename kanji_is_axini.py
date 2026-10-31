"""Shared five-kanji review batches. Selection never implies approval or completed artwork."""
import json
from pathlib import Path
import ortak

AGENTLER = {'hekayeci', 'komponent', 'mufettis', 'redaktor', 'testci', 'sekil'}
BOYUT = 5


def status():
    source = Path(ortak.KOK) / 'kotoba/veri/kanji.json'
    rows = json.loads(source.read_text(encoding='utf-8'))
    # Preserve the export's lesson/frequency ordering, including existing cards.
    seen = set()
    rows = [r for r in rows if not (r['kanji'] in seen or seen.add(r['kanji']))]
    total = (len(rows) + BOYUT - 1) // BOYUT
    state = Path(ortak.DURUM_DIZINI) / 'kanji-partiya.json'
    try:
        selected = json.loads(state.read_text(encoding='utf-8'))['partiya']
        if type(selected) is not int:
            selected = 1
    except (OSError, ValueError, KeyError, TypeError):
        selected = 1
    selected = max(1, min(selected, total or 1))
    batch = rows[(selected - 1) * BOYUT:selected * BOYUT]
    return {'partiya': selected, 'partiya_sayi': total, 'kanji_sayi': len(rows),
            'kanjiler': [{k: r.get(k) for k in ('kanji', 'ders', 'on', 'kun', 'az', 'en', 'ru', 'nümunə_sozler')} for r in batch],
            'sekil_status': 'gemini_desteklenir'}


def sec(number):
    current = status()
    if type(number) is not int or not 1 <= number <= current['partiya_sayi']:
        raise ValueError('Yanlış qrup nömrəsi')
    dest = Path(ortak.DURUM_DIZINI) / 'kanji-partiya.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix('.tmp')
    temp.write_text(json.dumps({'partiya': number}), encoding='utf-8')
    temp.replace(dest)
    return status()


def prompt_elave(prompt, batch):
    return (prompt + '\n\n## Aktiv kanji qrupu (iş başlayan andakı surət)\n'
            + f"Qrup: b{batch['partiya']:03d}. Mövcud kartlar da yenidən işlənir. "
            + 'Köhnə novbe.json əvəzinə bu siyahını istifadə et. İstifadəçi açıq başqa kanji göstəribsə onu üstün tut. '
            + f'Layihənin kökü: {ortak.KOK}. Nisbi fayl yollarını bu kökə görə oxu. '
            + 'Əvvəlki nəticələrdə yalnız eyni bNNN olan fayllara bax. '
            + 'Əlaqəli fayllar cikti/<agent>/*-bNNN-*.md; dərs datası kotoba/veri/kanji/NN.json. '
            + 'Bu qrup nömrəsi keyfiyyət təsdiqi deyil.\n'
            + json.dumps(batch['kanjiler'], ensure_ascii=False))
