#!/usr/bin/env python3
"""GitHub Actions'ta çalışır: 'sira' release'inden sıradaki videoyu indirip paylaşır.

  python ci_paylas.py oto                → TR saatine göre şu anki vakit henüz paylaşılmadıysa paylaş
  python ci_paylas.py sabah|ogle|aksam   → o vakte ait sıradaki videoyu paylaş
  python ci_paylas.py karusel            → sıradaki kaydırmalı gönderiyi paylaş
  python ci_paylas.py rapor              → haftalık istatistik raporu (GitHub Issue)
  python ci_paylas.py yorum              → yalnızca yorumlara yanıt ver
  ('oto' da vakti gelen karuseli paylaşır ve her çalışmada yorumlara yanıt verir; --dene: yayınlamadan dene)
  python ci_paylas.py yenile             → Instagram anahtarını yenile, şifreli olarak durum/token.enc'e yaz

Hangi videoların paylaşıldığı durum/paylasim_kaydi.csv'de tutulur (workflow bunu commit'ler).
Anahtar depoda yalnızca ENC_KEY secret'ı ile şifrelenmiş olarak durur.
"""
import datetime, json, os, subprocess, sys
from pathlib import Path

import requests

os.environ.setdefault("PAYLASIM_KAYDI", str(Path(__file__).resolve().parent / "durum" / "paylasim_kaydi.csv"))
import paylas  # noqa: E402

KOK = Path(__file__).resolve().parent
TOKEN_ENC = KOK / "durum" / "token.enc"
RELEASE = "sira"
TR = datetime.timezone(datetime.timedelta(hours=3))  # Türkiye'de yaz saati yok
# Vakit başlangıçları (TR). GitHub zamanlayıcısı gecikip atlayabildiği için workflow
# 10 dakikada bir çalışır; 'oto' o anki vakit bugün paylaşılmadıysa paylaşır.
VAKITLER = [("sabah", 8, 45), ("ogle", 12, 45), ("aksam", 19, 45)]
# Kaydırmalı gönderi: her gün 16:45 TR'den itibaren ('karusel' release'i)
KARUSEL, KARUSEL_GUNLER, KARUSEL_SAAT = "karusel", set(range(7)), (16, 45)


# Instagram "request limit" hatasında o iş için bu kadar beklenir (10 dakikada bir denemek limiti besler)
LIMIT_BEKLEME = datetime.timedelta(hours=2)


def limitte_mi(is_adi):
    """Bu iş yakın zamanda limite takıldıysa True (işaret dosyası durum/'a yazılır, workflow commit'ler)."""
    dosya = KOK / "durum" / f"limit_{is_adi}.txt"
    if not dosya.exists():
        return False
    return datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(dosya.read_text().strip()) < LIMIT_BEKLEME


def limit_isaretle(is_adi, limite_takildi):
    dosya = KOK / "durum" / f"limit_{is_adi}.txt"
    if limite_takildi:
        dosya.write_text(datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
    else:
        dosya.unlink(missing_ok=True)


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def sifrele(token):
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-pass", "env:ENC_KEY",
                    "-out", str(TOKEN_ENC)], input=token, text=True, check=True)


def paylasilanlar():
    if not paylas.KAYIT.exists():
        return set()
    return {satir.split(",")[1] for satir in paylas.KAYIT.read_text().splitlines() if satir.count(",") >= 2}


def kayit_satirlari():
    if not paylas.KAYIT.exists():
        return []
    satirlar = []
    for satir in paylas.KAYIT.read_text().splitlines():
        parca = satir.split(",")
        if len(parca) >= 3:
            zaman = datetime.datetime.fromisoformat(parca[0])
            if zaman.tzinfo is None:  # eski kayıtlar Actions'ta (UTC) yazıldı
                zaman = zaman.replace(tzinfo=datetime.timezone.utc)
            satirlar.append((zaman.astimezone(TR), parca[1]))
    return satirlar


def bugun_paylasildi_mi(kosul):
    bugun = datetime.datetime.now(TR).date()
    return any(zaman.date() == bugun and kosul(dosya) for zaman, dosya in kayit_satirlari())


def vakit_of(icerik, dosya):
    no = dosya.split("_")[0]
    return icerik.get(int(no), {}).get("vakit") if no.isdigit() else None


def oto_vakit(icerik):
    """Şu an hangi vakit paylaşılmalı? Bugün paylaşılmışsa ya da vakit gelmediyse None."""
    simdi = datetime.datetime.now(TR)
    vakit = None
    for ad, sa, dk in VAKITLER:
        if (simdi.hour, simdi.minute) >= (sa, dk):
            vakit = ad
    if vakit is None or bugun_paylasildi_mi(lambda d: vakit_of(icerik, d) == vakit):
        return None
    return vakit


def karusel_zamani():
    simdi = datetime.datetime.now(TR)
    return (simdi.weekday() in KARUSEL_GUNLER and (simdi.hour, simdi.minute) >= KARUSEL_SAAT
            and not bugun_paylasildi_mi(lambda d: d.startswith("K")))


def ilk_yorum_yaz(cfg, tur):
    """Az önce paylaşılan gönderiye (kayıttaki son satır) hesabın kendisinden soru yorumu."""
    try:
        import yorum
        medya_id = paylas.KAYIT.read_text().splitlines()[-1].split(",")[2]
        yorum.ilk_yorum(cfg, medya_id, tur)
    except Exception as e:
        print(f"::warning::İlk yorum yazılamadı: {e}")


def reels_paylas(cfg, icerik, vakit, yayinla):
    varliklar = sorted(gh("release", "view", RELEASE, "--json", "assets", "-q", ".assets[].name").split())
    yapilmis = paylasilanlar()
    adaylar = [a for a in varliklar if a.endswith(".mp4") and a not in yapilmis and vakit_of(icerik, a) == vakit]
    if not adaylar:
        raise RuntimeError(f"'{vakit}' için sırada video kalmadı! Yeni içerik üretip release'e yükle.")
    if len(adaylar) <= 7:
        print(f"::warning::'{vakit}' için sadece {len(adaylar)} video kaldı, yakında yeni içerik gerekecek.")
    hedef = KOK / "sira"
    hedef.mkdir(exist_ok=True)
    ad = adaylar[0]
    gh("release", "download", RELEASE, "-p", ad.replace(".mp4", ".txt"), "-D", str(hedef), "--clobber")
    paylas.paylas(cfg, hedef / ad, imzali_link(ad), yayinla=yayinla)
    if yayinla and not paylas.ZATEN_YAYINDA:
        ilk_yorum_yaz(cfg, vakit)
        try:  # hikâye olmazsa Reels yine paylaşılmış olur, iş başarısız sayılmaz
            paylas.hikaye(cfg, imzali_link(ad))
        except Exception as e:
            print(f"::warning::Hikâye paylaşılamadı: {e}")


def karusel_paylas(cfg, yayinla):
    varliklar = gh("release", "view", KARUSEL, "--json", "assets", "-q", ".assets[].name").split()
    yapilmis = paylasilanlar()
    adaylar = sorted({a.split("_")[0].split(".")[0] for a in varliklar} - yapilmis)
    if not adaylar:
        raise RuntimeError("Sırada kaydırmalı gönderi kalmadı! karusel.json'a ekleyip karusel.py ile üret.")
    if len(adaylar) <= 3:
        print(f"::warning::Sadece {len(adaylar)} kaydırmalı gönderi kaldı.")
    ad = adaylar[0]
    gorseller = sorted((a for a in varliklar if a.startswith(ad + "_") and a.endswith(".jpg")),
                       key=lambda a: int(a.rsplit("_", 1)[1].split(".")[0]))
    hedef = KOK / "karusel"
    hedef.mkdir(exist_ok=True)
    gh("release", "download", KARUSEL, "-p", f"{ad}.txt", "-D", str(hedef), "--clobber")
    aciklama = (hedef / f"{ad}.txt").read_text()
    paylas.karusel(cfg, ad, aciklama, [imzali_link(g, KARUSEL) for g in gorseller], yayinla=yayinla)
    if yayinla and not paylas.ZATEN_YAYINDA:
        ilk_yorum_yaz(cfg, "karusel")


def main():
    is_ = sys.argv[1]
    yayinla = "--dene" not in sys.argv
    cfg = paylas.ayar()
    icerik = {o["id"]: o for o in json.loads((KOK / "icerik.json").read_text())}

    if is_ in ("yenile", "rapor"):
        if is_ == "yenile":
            yeni, gun = paylas.yenile(cfg)
            sifrele(yeni)
        try:  # haftalık rapor; olmazsa anahtar yenileme yine başarılı sayılır
            import rapor
            rapor.main(cfg, gonder=yayinla)
        except Exception as e:
            print(f"::warning::Haftalık rapor çıkarılamadı: {e}")
            if is_ == "rapor":
                raise
        return

    hata = False
    if is_ in ("sabah", "ogle", "aksam"):
        reels_paylas(cfg, icerik, is_, yayinla)
    elif is_ == "karusel":
        karusel_paylas(cfg, yayinla)
    elif is_ == "oto":
        # her iş ayrı: biri hata verirse diğerleri yine çalışsın
        vakit = oto_vakit(icerik)
        for ad, kosul, is_fn in [(f"Reels ({vakit})", vakit, lambda: reels_paylas(cfg, icerik, vakit, yayinla)),
                                 ("Karusel", karusel_zamani(), lambda: karusel_paylas(cfg, yayinla))]:
            if not kosul:
                continue
            anahtar = ad.split(" ")[0].lower()
            if limitte_mi(anahtar):
                print(f"::warning::{ad}: Instagram limiti nedeniyle {LIMIT_BEKLEME} bekleniyor, atlandı.")
                continue
            print(f"→ {ad}")
            try:
                is_fn()
                limit_isaretle(anahtar, False)
            except Exception as e:
                print(f"::error::{ad} paylaşılamadı: {e}")
                limit_isaretle(anahtar, "request limit" in str(e).lower())
                hata = True
    # yorumlara yarım saatte bir bak (Meta'yı gereksiz istekle yormamak için)
    if is_ == "yorum" or (is_ == "oto" and datetime.datetime.now(TR).minute % 30 < 10):
        try:
            import yorum
            yorum.yanitla(cfg, gonder=yayinla)
        except Exception as e:
            print(f"::warning::Yorumlar yanıtlanamadı: {e}")
    if hata:
        sys.exit(1)


def imzali_link(ad, release=RELEASE):
    """Gizli depodaki release dosyası için GitHub'ın verdiği birkaç dakikalık imzalı indirme linki.
    Depo gizli kalır; link kısa sürede kendiliğinden geçersizleşir."""
    api_url = gh("release", "view", release, "--json", "assets",
                 "-q", f'.assets[] | select(.name=="{ad}") | .apiUrl').strip()
    r = requests.get(api_url, allow_redirects=False, timeout=30, headers={
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/octet-stream"})
    if r.status_code not in (301, 302, 303, 307) or "Location" not in r.headers:
        raise RuntimeError(f"İmzalı link alınamadı ({r.status_code})")
    return r.headers["Location"]


if __name__ == "__main__":
    main()
