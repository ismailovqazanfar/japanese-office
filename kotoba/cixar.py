#!/usr/bin/env python3
"""Kotoba no Tabi datasını agentlərin oxuya biləcəyi kiçik fayllara çıxarır və kanji boşluq hesabatı hazırlayır.

Sayt faylı ~50 MB-dır, agent onu birbaşa oxuya bilməz. Bu skript lazım olan hissələri ayırır:
  kotoba/veri/kanji.json      dərs kanjiləri + kart məlumatı (mənşə, yadda saxlama hekayəsi, komponentlər)
  kotoba/veri/lugat.json      dərslərin söz siyahısı
  kotoba/veri/novbe.json      kartı olmayan kanjilər (dərs sırası ilə) – Hekayəçi buradan götürür
  kotoba/veri/hesabat.md      boşluqlar və problemlər (oxumaq üçün)

İstifadə:
  python3 kotoba/cixar.py                       # kotoba-no-tabi qovluğunu özü axtarır
  python3 kotoba/cixar.py ~/kotoba-no-tabi      # və ya yolu göstər (index.html olan qovluq ya da html faylı)
Yalnız Python standart kitabxanası lazımdır.
"""
import gzip
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

KOK = os.path.dirname(os.path.abspath(__file__))
VERI = os.path.join(KOK, "veri")
EV = os.path.expanduser("~")
AXTAR = [
    os.path.join(os.path.dirname(KOK), "..", "kotoba-no-tabi"),
    os.path.join(EV, "kotoba-no-tabi"),
    os.path.join(EV, "Documents", "GitHub", "kotoba-no-tabi"),
    os.path.join(EV, "Desktop", "kotoba-no-tabi"),
    os.path.join(EV, "OneDrive", "Documents", "GitHub", "kotoba-no-tabi"),
]
KANJI = re.compile(r"[一-鿿㐀-䶿々]")
TIRE = "—"


def mənbə_tap(arg):
    yollar = [arg] if arg else AXTAR
    for y in yollar:
        y = os.path.abspath(os.path.expanduser(y))
        if os.path.isfile(y) and y.endswith(".html"):
            return y, os.path.dirname(y)
        for ad in ("index.html", "Kotoba_no_Tabi.html"):
            if os.path.isfile(os.path.join(y, ad)):
                return os.path.join(y, ad), y
    sys.exit("kotoba-no-tabi tapılmadı. Yolu göstər: python3 kotoba/cixar.py <qovluq və ya html faylı>")


def json_obyekt(html, ad):
    """`const AD={...};` sətrini tapıb JSON kimi oxuyur (mötərizələri sayaraq)."""
    i = html.find(f"const {ad}=")
    if i < 0:
        return None
    j = html.index("{", i)
    d, k, sim = 0, j, None
    while k < len(html):
        c = html[k]
        if sim:
            if c == "\\":
                k += 2
                continue
            if c == sim:
                sim = None
        elif c == '"':
            sim = c
        elif c == "{":
            d += 1
        elif c == "}":
            d -= 1
            if d == 0:
                return json.loads(html[j:k + 1])
        k += 1
    return None


def kartlar_oxu(html, qovluq):
    """Kanji kartları (k4): əvvəl k4.bin, sonra k4.js, sonra html-in içi."""
    xam = None
    b = os.path.join(qovluq, "k4.bin")
    if os.path.isfile(b):
        xam = open(b, "rb").read()
    else:
        js = os.path.join(qovluq, "k4.js")
        mətn = open(js, encoding="utf-8").read() if os.path.isfile(js) else html
        m = re.search(r'KOTOBA_K4\s*=\s*"([A-Za-z0-9+/=]+)"', mətn)
        if m:
            import base64
            xam = base64.b64decode(m.group(1))
    if not xam:
        return {}
    try:
        xam = gzip.decompress(xam)
    except OSError:
        pass
    return json.loads(xam).get("k", {})


def əsas(arg):
    html_yolu, qovluq = mənbə_tap(arg)
    html = open(html_yolu, encoding="utf-8").read()
    KJ = json_obyekt(html, "KJ") or {}
    VOC = json_obyekt(html, "VOC") or {}
    kart = kartlar_oxu(html, qovluq)
    if not KJ:
        sys.exit("Saytda kanji cədvəli (KJ) tapılmadı.")
    dersler = {}
    dp = os.path.join(VERI, "dersler.json")
    if os.path.isfile(dp):
        dersler = {d["n"]: d for d in json.load(open(dp, encoding="utf-8"))}

    # söz siyahısı və kanjilərin ilk istifadəsi
    lugat, ilk = [], {}
    for n_str, sozler in VOC.items():
        if not n_str.isdigit():
            continue
        n = int(n_str)
        for s in sozler:
            yazilis = s[0] if s else ""
            lugat.append({"ders": n, "soz": yazilis, "oxunus": s[1] if len(s) > 1 else "",
                          "romaji": s[2] if len(s) > 2 else "", "az": s[3] if len(s) > 3 else ""})
            for ch in KANJI.findall(yazilis):
                if ch not in ilk or n < ilk[ch]:
                    ilk[ch] = n
    soz_say = defaultdict(int)
    for s in lugat:
        for ch in set(KANJI.findall(s["soz"])):
            soz_say[ch] += 1

    # kanji cədvəli
    kanjilər = []
    for ch, v in KJ.items():
        k = kart.get(ch) or {}
        o, kk = k.get("o") or [], k.get("kk") or []
        kanjilər.append({
            "kanji": ch, "on": v[0], "kun": v[1], "az": v[2], "en": v[3], "ru": v[4], "ders": v[5],
            "kart": bool(k), "komponent": [s[0] for s in (k.get("sk") or [])],
            "mense": {"az": o[0] if len(o) > 0 else "", "en": o[1] if len(o) > 1 else "", "ru": o[2] if len(o) > 2 else ""},
            "hekaye": {"az": kk[0] if len(kk) > 0 else "", "en": kk[1] if len(kk) > 1 else "", "ru": kk[2] if len(kk) > 2 else ""},
            "ilk_soz_dersi": ilk.get(ch), "soz_sayi": soz_say.get(ch, 0),
            "nümunə_sozler": [s["soz"] + " (" + s["oxunus"] + ") " + s["az"] for s in lugat if ch in s["soz"]][:4],
        })
    kanjilər.sort(key=lambda x: (x["ders"] == 0, x["ders"], -x["soz_sayi"]))  # 0 = dərsə bağlanmamış kanjilər, sonda

    # problemlər
    kartsiz = [x for x in kanjilər if not x["kart"]]
    kartlar_derssiz = sorted(set(kart) - set(KJ))
    eksik_mena = [x for x in kanjilər if not (x["az"] and x["en"] and x["ru"])]
    eksik_oxunus = [x for x in kanjilər if not (x["on"] or x["kun"])]
    eksik_kart_metni = [x for x in kanjilər if x["kart"] and not all(x["hekaye"][d] and x["mense"][d] for d in ("az", "en", "ru"))]
    zeif_hekaye = [x for x in kanjilər if x["kart"] and x["hekaye"]["az"] and
                   (len(x["hekaye"]["az"]) < 60 or x["kanji"] not in x["hekaye"]["az"])]
    tire = [x for x in kanjilər if any(TIRE in t for t in (*x["hekaye"].values(), *x["mense"].values(), x["az"]))]
    dersde_yox = sorted({ch for ch, n in ilk.items() if ch not in KJ and n <= 35}, key=lambda c: ilk[c])
    erken = [x for x in kanjilər if x["ilk_soz_dersi"] and x["ilk_soz_dersi"] < x["ders"]]
    istifadesiz = [x for x in kanjilər if not x["ilk_soz_dersi"]]

    os.makedirs(VERI, exist_ok=True)
    yaz = lambda ad, d: json.dump(d, open(os.path.join(VERI, ad), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    yaz("kanji.json", kanjilər)
    # agent az token xərcləsin deyə dərs-dərs kiçik fayllar
    kd = os.path.join(VERI, "kanji")
    os.makedirs(kd, exist_ok=True)
    for f in os.listdir(kd):
        if f.endswith(".json"):
            os.remove(os.path.join(kd, f))
    dersler_kanji = defaultdict(list)
    for x in kanjilər:
        dersler_kanji[x["ders"]].append(x)
    for n, xs in dersler_kanji.items():
        yaz(os.path.join("kanji", f"{n:02d}.json"), xs)
    yaz("lugat.json", lugat)
    yaz("novbe.json", [{"kanji": x["kanji"], "ders": x["ders"], "on": x["on"], "kun": x["kun"], "az": x["az"],
                        "en": x["en"], "ru": x["ru"], "nümunə_sozler": x["nümunə_sozler"]} for x in kartsiz])

    def siyahi(xs, f=lambda x: x["kanji"], limit=200):
        s = " ".join(f(x) for x in xs[:limit])
        return s + (f" … (+{len(xs) - limit})" if len(xs) > limit else "")

    sətir = [f"# Kotoba no Tabi: kanji hesabatı ({datetime.now():%Y-%m-%d %H:%M})", "",
             f"Mənbə: `{html_yolu}`", "",
             "## Ümumi", "",
             f"| Göstərici | Say |", "|---|---|",
             f"| Dərs kanjiləri (KJ) | {len(kanjilər)} |",
             f"| Kartı olan | {len(kanjilər) - len(kartsiz)} |",
             f"| **Kartı olmayan** | **{len(kartsiz)}** |",
             f"| Kartı var, dərsdə yoxdur | {len(kartlar_derssiz)} |",
             f"| Mənası natamam (az/en/ru) | {len(eksik_mena)} |",
             f"| Oxunuşu boş | {len(eksik_oxunus)} |",
             f"| Kart mətni natamam (mənşə/hekayə, 3 dil) | {len(eksik_kart_metni)} |",
             f"| Hekayə qısadır və ya kanjinin özü keçmir | {len(zeif_hekaye)} |",
             f"| Uzun tire olan mətnlər | {len(tire)} |",
             f"| Sözlərdə var, kanji cədvəlində yoxdur (1–35) | {len(dersde_yox)} |",
             f"| Sözdə dərsindən əvvəl işlənir | {len(erken)} |",
             f"| Heç bir sözdə işlənmir | {len(istifadesiz)} |", "",
             "## Kartı olmayan kanjilər (dərs üzrə; 0 = heç bir dərsə bağlanmayıb)", ""]
    by = defaultdict(list)
    for x in kartsiz:
        by[x["ders"]].append(x)
    for n in sorted(by):
        ad = dersler.get(n, {}).get("az", "")
        sətir.append(f"- **{n}-ci dərs** {('(' + ad + ')') if ad else ''}: {siyahi(by[n])}")
    sətir += ["", "## Növbəti 5 kart (Hekayəçi üçün)", ""]
    for x in kartsiz[:5]:
        sətir.append(f"- {x['kanji']} – {x['az']} · {x['on']} / {x['kun']} · {x['ders']}-ci dərs · nümunə: {', '.join(x['nümunə_sozler'][:2]) or 'yoxdur'}")
    sətir += ["", "## Mənası və ya oxunuşu natamam", "", siyahi(eksik_mena + eksik_oxunus) or "yoxdur",
              "", "## Kart mətni natamam", "", siyahi(eksik_kart_metni) or "yoxdur",
              "", "## Hekayə qısadır və ya kanjinin özü keçmir", "", siyahi(zeif_hekaye) or "yoxdur",
              "", "## Uzun tire olan mətnlər", "", siyahi(tire) or "yoxdur",
              "", "## Sözlərdə işlənir, amma kanji cədvəlində yoxdur", "",
              siyahi(dersde_yox, f=lambda c: f"{c}({ilk[c]})") or "yoxdur",
              "", "## Sözdə dərsindən əvvəl işlənir (kanji: dərs → ilk söz dərsi)", "",
              siyahi(erken, f=lambda x: f"{x['kanji']}:{x['ders']}→{x['ilk_soz_dersi']}") or "yoxdur",
              "", "## Kartı var, amma dərs kanjisi deyil", "", " ".join(kartlar_derssiz) or "yoxdur", ""]
    open(os.path.join(VERI, "hesabat.md"), "w", encoding="utf-8").write("\n".join(sətir))
    print(f"Hazırdır: {len(kanjilər)} kanji, {len(kartsiz)} kartsız, {len(lugat)} söz → {os.path.relpath(VERI)}/")


if __name__ == "__main__":
    əsas(sys.argv[1] if len(sys.argv) > 1 else None)
