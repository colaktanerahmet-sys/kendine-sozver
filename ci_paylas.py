#!/usr/bin/env python3
"""GitHub Actions'ta çalışır: 'sira' release'inden sıradaki videoyu indirip paylaşır.

  python ci_paylas.py oto                → TR saatine göre şu anki vakit henüz paylaşılmadıysa paylaş
  python ci_paylas.py sabah|ogle|aksam   → o vakte ait sıradaki videoyu paylaş
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
# saatte bir çalışır; 'oto' o anki vakit bugün paylaşılmadıysa paylaşır.
VAKITLER = [("sabah", 8, 45), ("ogle", 12, 45), ("aksam", 19, 45)]


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


def oto_vakit(icerik):
    """Şu an hangi vakit paylaşılmalı? Bugün paylaşılmışsa ya da vakit gelmediyse None."""
    simdi = datetime.datetime.now(TR)
    vakit = None
    for ad, sa, dk in VAKITLER:
        if (simdi.hour, simdi.minute) >= (sa, dk):
            vakit = ad
    if vakit is None:
        return None
    for zaman, dosya in kayit_satirlari():
        if zaman.date() == simdi.date() and icerik.get(int(dosya.split("_")[0]), {}).get("vakit") == vakit:
            return None
    return vakit


def main():
    vakit = sys.argv[1]
    cfg = paylas.ayar()
    icerik = {o["id"]: o for o in json.loads((KOK / "icerik.json").read_text())}

    if vakit == "oto":
        vakit = oto_vakit(icerik)
        if vakit is None:
            print("Şu an paylaşılacak bir şey yok (vakit gelmedi ya da bugün zaten paylaşıldı).")
            return
        print(f"Otomatik vakit: {vakit}")

    if vakit == "yenile":
        yeni, gun = paylas.yenile(cfg)
        sifrele(yeni)
        return

    varliklar = sorted(gh("release", "view", RELEASE, "--json", "assets", "-q", ".assets[].name").split())
    yapilmis = paylasilanlar()
    adaylar = [a for a in varliklar if a.endswith(".mp4") and a not in yapilmis
               and icerik.get(int(a.split("_")[0]), {}).get("vakit") == vakit]
    if not adaylar:
        sys.exit(f"'{vakit}' için sırada video kalmadı! Yeni içerik üretip release'e yükle.")
    if len(adaylar) <= 7:
        print(f"::warning::'{vakit}' için sadece {len(adaylar)} video kaldı, yakında yeni içerik gerekecek.")

    hedef = KOK / "sira"
    hedef.mkdir(exist_ok=True)
    ad = adaylar[0]
    gh("release", "download", RELEASE, "-p", ad.replace(".mp4", ".txt"), "-D", str(hedef), "--clobber")
    yayinla = "--dene" not in sys.argv
    paylas.paylas(cfg, hedef / ad, imzali_link(ad), yayinla=yayinla)
    if yayinla:
        try:  # hikâye olmazsa Reels yine paylaşılmış olur, iş başarısız sayılmaz
            paylas.hikaye(cfg, imzali_link(ad))
        except Exception as e:
            print(f"::warning::Hikâye paylaşılamadı: {e}")


def imzali_link(ad):
    """Gizli depodaki release dosyası için GitHub'ın verdiği birkaç dakikalık imzalı indirme linki.
    Depo gizli kalır; link kısa sürede kendiliğinden geçersizleşir."""
    api_url = gh("release", "view", RELEASE, "--json", "assets",
                 "-q", f'.assets[] | select(.name=="{ad}") | .apiUrl').strip()
    r = requests.get(api_url, allow_redirects=False, timeout=30, headers={
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/octet-stream"})
    if r.status_code not in (301, 302, 303, 307) or "Location" not in r.headers:
        raise RuntimeError(f"İmzalı link alınamadı ({r.status_code})")
    return r.headers["Location"]


if __name__ == "__main__":
    main()
