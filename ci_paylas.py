#!/usr/bin/env python3
"""GitHub Actions'ta çalışır: 'sira' release'inden sıradaki videoyu indirip paylaşır.

  python ci_paylas.py sabah|ogle|aksam   → o vakte ait sıradaki videoyu paylaş
  python ci_paylas.py yenile             → Instagram anahtarını yenile, şifreli olarak durum/token.enc'e yaz

Hangi videoların paylaşıldığı durum/paylasim_kaydi.csv'de tutulur (workflow bunu commit'ler).
Anahtar depoda yalnızca ENC_KEY secret'ı ile şifrelenmiş olarak durur.
"""
import json, os, subprocess, sys
from pathlib import Path

os.environ.setdefault("PAYLASIM_KAYDI", str(Path(__file__).resolve().parent / "durum" / "paylasim_kaydi.csv"))
import paylas  # noqa: E402

KOK = Path(__file__).resolve().parent
TOKEN_ENC = KOK / "durum" / "token.enc"
RELEASE = "sira"


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def sifrele(token):
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-pass", "env:ENC_KEY",
                    "-out", str(TOKEN_ENC)], input=token, text=True, check=True)


def paylasilanlar():
    if not paylas.KAYIT.exists():
        return set()
    return {satir.split(",")[1] for satir in paylas.KAYIT.read_text().splitlines() if satir.count(",") >= 2}


def main():
    vakit = sys.argv[1]
    cfg = paylas.ayar()

    if vakit == "yenile":
        yeni, gun = paylas.yenile(cfg)
        sifrele(yeni)
        return

    icerik = {o["id"]: o for o in json.loads((KOK / "icerik.json").read_text())}
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
    gh("release", "download", RELEASE, "-p", ad, "-p", ad.replace(".mp4", ".txt"), "-D", str(hedef), "--clobber")
    paylas.paylas(cfg, hedef / ad)


if __name__ == "__main__":
    main()
