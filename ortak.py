"""Yapon Ofisi ortaq köməkçiləri: yollar, agent cədvəli, hadisə jurnalı, vəziyyət faylları.
Windows, macOS və Linux-da işləyir (fcntl yalnız POSIX-də var, Windows-da msvcrt istifadə olunur)."""
import json
import os
import re
import time
from datetime import datetime, timezone

WINDOWS = os.name == "nt"
if WINDOWS:
    import msvcrt
else:
    import fcntl

KOK = os.path.dirname(os.path.abspath(__file__))
# Yapılandırma: ajanlar.example.json'ı ajanlar.json olarak kopyala (ajanlar.json .gitignore'da).
AJANLAR_DOSYASI = os.environ.get("OFIS_AJANLAR", os.path.join(KOK, "ajanlar.json"))
OLAYLAR = os.path.join(KOK, "olaylar.jsonl")
DURUM_DIZINI = os.path.join(KOK, "durum")
KOSU_DIZINI = os.path.join(KOK, "kosular")
CIKTI_DIZINI = os.path.join(KOK, "cikti")
HAFIZA_DIZINI = os.path.join(KOK, "hafiza")

MAKS_GIRDI = 4000
MAKS_HAFIZA_EKI = 1200
AJAN_ID_DESENI = re.compile(r"^[a-z0-9-]{1,40}$")
# Oda id'si serbest (sahnede yoksa otomatik açılır) ama prompt'a ve olaylara girdiği için harf/rakam/_/- ve en çok 40 karakter.
ODA_ID_DESENI = re.compile(r"[\w-]{1,40}")


def simdi_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def bugun():
    return datetime.now().strftime("%Y-%m-%d")


class YapilandirmaHatasi(Exception):
    pass


def ajanlari_yukle():
    try:
        with open(AJANLAR_DOSYASI, encoding="utf-8") as f:
            veri = json.load(f)
    except FileNotFoundError as e:
        raise YapilandirmaHatasi(
            f"{os.path.basename(AJANLAR_DOSYASI)} yoxdur. Əvvəlcə: cp ornek/ajanlar.kotoba.json ajanlar.json") from e
    if not isinstance(veri, dict) or not isinstance(veri.get("ajanlar"), list):
        raise YapilandirmaHatasi("ajanlar.json içində 'ajanlar' siyahısı olmalıdır")
    # Merge new workflow actions in memory; preserve user paths, models and tool restrictions.
    with open(os.path.join(KOK, "ajanlar.example.json"), encoding="utf-8") as f:
        sablon = json.load(f)
    mevcut = {a["id"]: a for a in veri["ajanlar"]}
    for yeni in sablon["ajanlar"]:
        if yeni["id"] == "sekil" and "sekil" not in mevcut:
            veri["ajanlar"].append(yeni)
        elif yeni["id"] in mevcut:
            hedef = mevcut[yeni["id"]]
            gorevler = hedef.setdefault("hazir_gorevler", [])
            etiketler = {g["etiket"] for g in gorevler}
            for g in yeni.get("hazir_gorevler", []):
                if g["etiket"].startswith("Aktiv ") and g["etiket"] not in etiketler:
                    gorevler.insert(0, g)
    if any(a["id"] == "sekil" for a in veri["ajanlar"]):
        odalar = veri.setdefault("odalar", [])
        if not any(o.get("id") == "sekil" for o in odalar):
            odalar.append(next(o for o in sablon["odalar"] if o["id"] == "sekil"))
    tablo = {}
    for ajan in veri["ajanlar"]:
        if not AJAN_ID_DESENI.match(ajan["id"]):
            raise ValueError(f"yanlış agent id: {ajan['id']!r}")
        oda = ajan.get("oda") or "genel"
        if not isinstance(oda, str) or not ODA_ID_DESENI.fullmatch(oda):
            raise ValueError(f"yanlış otaq id: {oda!r} (agent {ajan['id']})")
        cwd = cwd_hell(ajan.get("cwd"))
        tablo[ajan["id"]] = {**ajan, "oda": oda, "cwd": cwd, "kurulu": bool(cwd) and os.path.isdir(cwd)}
    return veri, tablo


def cwd_hell(cwd):
    """~ açılır; nisbi yol (\".\", \"kotoba\") bu qovluğa görə həll olunur ki, server haradan işə salınsa da eyni olsun."""
    if not cwd:
        return ""
    cwd = os.path.expanduser(cwd)
    return os.path.normpath(cwd if os.path.isabs(cwd) else os.path.join(KOK, cwd))


def ayarlar(veri):
    """Arayüz ayarları: kullanıcı adı (selamlama) ve marka. İkisi de isteğe bağlı."""
    a = veri.get("ayarlar") if isinstance(veri.get("ayarlar"), dict) else {}
    return {"kullanici": str(a.get("kullanici") or "")[:40], "marka": str(a.get("marka") or "Yapon Ofisi")[:40]}


def olay_yaz(olay):
    """olaylar.jsonl'e tek satır ekler (süreçler arası kilitli)."""
    satir = json.dumps({"zaman": simdi_iso(), **olay}, ensure_ascii=False)
    with open(OLAYLAR, "a", encoding="utf-8") as f:
        _kilitle(f)
        try:
            f.write(satir + "\n")
            f.flush()
        finally:
            _ac(f)


def _kilitle(f):
    if WINDOWS:
        for _ in range(200):  # Windows-da kilid gözləmir, özümüz təkrar yoxlayırıq (~10 sn)
            try:
                f.seek(0, os.SEEK_END)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.05)
    else:
        fcntl.flock(f, fcntl.LOCK_EX)


def _ac(f):
    try:
        if WINDOWS:
            f.seek(0, os.SEEK_END)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        pass


def durum_yolu(ajan_id):
    return os.path.join(DURUM_DIZINI, f"{ajan_id}.json")


def durum_oku(ajan_id):
    try:
        with open(durum_yolu(ajan_id), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def durum_yaz(ajan_id, durum):
    gecici = durum_yolu(ajan_id) + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False, indent=1)
    os.replace(gecici, durum_yolu(ajan_id))


def surec_yasiyor(pid):
    if not pid:
        return False
    if WINDOWS:
        # Windows-da os.kill(pid, 0) prosesi YOXLAMIR, dayandırır. Ona görə WinAPI ilə soruşuruq.
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        kod = ctypes.c_ulong()
        try:
            return bool(k32.GetExitCodeProcess(h, ctypes.byref(kod))) and kod.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True


def ajan_mesgul(ajan_id):
    """Agent indi işləyirmi? Ölü prosesdən qalan 'calisiyor' qeydini məşğul saymır."""
    d = durum_oku(ajan_id)
    if not d or d.get("durum") not in ("basliyor", "calisiyor"):
        return False
    if surec_yasiyor(d.get("pid")):
        return True
    # pəncərə açılarkən pid hələ yazılmamış ola bilər
    return d.get("durum") == "basliyor" and time.time() - d.get("baslangic_ts", 0) < 30



def ajan_ortami():
    """Image API credentials belong to the server, not Claude subprocesses."""
    return {k: v for k, v in os.environ.items() if k not in ('GEMINI_API_KEY', 'GOOGLE_API_KEY')}
