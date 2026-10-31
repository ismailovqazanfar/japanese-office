"""Shared five-kanji batches. Only kanji that need work are queued (no card, weak or incomplete card,
or listed in durum/kanji-elave.json). Selection never implies approval or completed artwork."""
import json
from pathlib import Path
import ortak

AGENTLER = {'hekayeci', 'komponent', 'mufettis', 'redaktor', 'testci', 'sekil'}
BOYUT = 5
TIRE = '\u2014'


def sebeb(r):
    """Why this kanji needs work, or None when its card is fine."""
    if not r.get('kart'):
        return 'kartsiz'
    h, m = r.get('hekaye') or {}, r.get('mense') or {}
    if not all(h.get(d) and m.get(d) for d in ('az', 'en', 'ru')):
        return 'natamam'
    if len(h['az']) < 60 or r['kanji'] not in h['az']:
        return 'zeif_hekaye'
    if any(TIRE in t for t in (*h.values(), *m.values())):
        return 'uzun_tire'
    return None


def elave():
    """Kanji the user explicitly asked to redo: durum/kanji-elave.json = ["字", ...]."""
    try:
        v = json.loads((Path(ortak.DURUM_DIZINI) / 'kanji-elave.json').read_text(encoding='utf-8'))
        return {c for c in v if isinstance(c, str)} if isinstance(v, list) else set()
    except (OSError, ValueError):
        return set()


def status():
    source = Path(ortak.KOK) / 'kotoba/veri/kanji.json'
    rows = json.loads(source.read_text(encoding='utf-8'))
    # Preserve the export's lesson/frequency ordering, including existing cards.
    seen = set()
    rows = [r for r in rows if not (r['kanji'] in seen or seen.add(r['kanji']))]
    hamisi, istek = len(rows), elave()
    for r in rows:
        r['sebeb'] = 'istifadeci' if r['kanji'] in istek else sebeb(r)
    rows = [r for r in rows if r['sebeb']]
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
    return {'partiya': selected, 'partiya_sayi': total, 'kanji_sayi': len(rows), 'hamisi': hamisi,
            'kanjiler': [{k: r.get(k) for k in ('kanji', 'sebeb', 'ders', 'on', 'kun', 'az', 'en', 'ru', 'nümunə_sozler')} for r in batch],
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
            + f"Qrup: b{batch['partiya']:03d}. Yalnız bu siyahıdakı kanjilər işlənir, 'sebeb' sahəsinə görə: "
            + 'kartsiz = yeni kart; natamam = çatışmayan dil/sahəni tamamla; zeif_hekaye = hekayəni gücləndir; '
            + 'uzun_tire = tireni düzəlt; istifadeci = istifadəçi açıq istədi, tam yenidən hazırla. '
            + 'Kartın yaxşı hissəsini saxla, mənşəni yalnız səhvdirsə dəyiş. '
            + 'Köhnə novbe.json əvəzinə bu siyahını istifadə et. İstifadəçi açıq başqa kanji göstəribsə onu üstün tut. '
            + f'Layihənin kökü: {ortak.KOK}. Nisbi fayl yollarını bu kökə görə oxu. '
            + 'Əvvəlki nəticələrdə yalnız eyni bNNN olan fayllara bax. '
            + 'Əlaqəli fayllar cikti/<agent>/*-bNNN-*.md; dərs datası kotoba/veri/kanji/NN.json. '
            + 'Bu qrup nömrəsi keyfiyyət təsdiqi deyil.\n'
            + json.dumps(batch['kanjiler'], ensure_ascii=False))
