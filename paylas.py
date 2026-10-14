#!/usr/bin/env python3
"""sira/ klasöründeki sıradaki videoyu Instagram'a Reels olarak paylaşır → paylasildi/

Instagram videoyu bir linkten indirir; GitHub'da ci_paylas.py geçici imzalı release linki verir.
Kullanım:
  .venv/bin/python paylas.py --kontrol      # anahtar + günlük limit kontrolü, paylaşım YOK
  .venv/bin/python paylas.py                # sıradaki videoyu paylaş
  .venv/bin/python paylas.py --vakit sabah  # sıradaki sabah videosunu paylaş
  .venv/bin/python paylas.py --yenile       # anahtarı 60 gün uzat
"""
import argparse, datetime, json, os, shutil, sys, time
from pathlib import Path

import requests

KOK = Path(__file__).resolve().parent
API = "https://graph.instagram.com/v23.0"
CFG_YOL = KOK / "config.json"
KAYIT = Path(os.environ.get("PAYLASIM_KAYDI", KOK / "paylasim_kaydi.csv"))


def ayar():
    cfg = json.loads(CFG_YOL.read_text()) if CFG_YOL.exists() else {}
    # GitHub Actions'ta anahtar ortam değişkeninden gelir
    cfg["ig_access_token"] = os.environ.get("IG_ACCESS_TOKEN") or cfg.get("ig_access_token")
    cfg["ig_user_id"] = os.environ.get("IG_USER_ID") or cfg.get("ig_user_id")
    if not cfg["ig_access_token"] or not cfg["ig_user_id"]:
        sys.exit("Instagram anahtarı yok (config.json ya da IG_ACCESS_TOKEN/IG_USER_ID).")
    return cfg


def cevap(r):
    try:
        veri = r.json()
    except ValueError:
        veri = {"ham": r.text}
    if r.status_code >= 400 or "error" in veri:
        hata = veri.get("error", veri)
        raise RuntimeError(f"Instagram hatası ({r.status_code}): {hata.get('message', hata)}")
    return veri


def kontrol(cfg):
    t = cfg["ig_access_token"]
    ben = cevap(requests.get(f"{API}/me", params={"fields": "username,account_type", "access_token": t}, timeout=30))
    limit = cevap(requests.get(f"{API}/{cfg['ig_user_id']}/content_publishing_limit",
                               params={"fields": "quota_usage,config", "access_token": t}, timeout=30))
    d = (limit.get("data") or [{}])[0]
    print(f"Hesap @{ben['username']} ({ben.get('account_type')}) · son 24 saatte {d.get('quota_usage', '?')}"
          f"/{d.get('config', {}).get('quota_total', '?')} paylaşım")


def yenile(cfg):
    veri = cevap(requests.get(f"{API.rsplit('/', 1)[0]}/refresh_access_token",
                              params={"grant_type": "ig_refresh_token", "access_token": cfg["ig_access_token"]},
                              timeout=30))
    gun = veri.get("expires_in", 0) // 86400
    if CFG_YOL.exists() and not os.environ.get("IG_ACCESS_TOKEN"):
        c = json.loads(CFG_YOL.read_text()); c["ig_access_token"] = veri["access_token"]
        CFG_YOL.write_text(json.dumps(c, ensure_ascii=False, indent=1)); CFG_YOL.chmod(0o600)
    print(f"Anahtar yenilendi, {gun} gün geçerli.")
    return veri["access_token"], gun


def siradaki(vakit):
    icerik = {o["id"]: o for o in json.loads((KOK / "icerik.json").read_text())}
    for mp4 in sorted((KOK / "sira").glob("*.mp4")):
        oge = icerik.get(int(mp4.stem.split("_")[0]))
        if vakit is None or (oge and oge.get("vakit") == vakit):
            return mp4
    return None


def paylas(cfg, mp4, video_url, yayinla=True):
    """video_url: Instagram'ın videoyu indireceği herkese açık (geçici olabilir) link.
    Instagram Login API'si doğrudan yüklemeyi (resumable) kabul etmiyor; link şart."""
    t, uid = cfg["ig_access_token"], cfg["ig_user_id"]
    aciklama = mp4.with_suffix(".txt").read_text() if mp4.with_suffix(".txt").exists() else ""

    # 1) kapsayıcı oluştur — Instagram videoyu bu andan itibaren linkten indirir
    kap = cevap(requests.post(f"{API}/{uid}/media", timeout=60, data={
        "media_type": "REELS", "video_url": video_url, "caption": aciklama,
        "share_to_feed": "true", "thumb_offset": "2000", "access_token": t}))
    kid = kap["id"]

    # 2) Instagram'ın videoyu işlemesini bekle
    for _ in range(60):
        durum = cevap(requests.get(f"{API}/{kid}", params={"fields": "status_code,status", "access_token": t},
                                   timeout=30))
        if durum.get("status_code") == "FINISHED":
            break
        if durum.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Video işlenemedi: {durum.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Video 10 dakikada işlenmedi.")
    if not yayinla:
        print(f"Deneme başarılı ✓ Instagram {mp4.name} videosunu indirip işledi (YAYINLANMADI).")
        return None

    # 3) yayınla
    yayin = cevap(requests.post(f"{API}/{uid}/media_publish", data={"creation_id": kid, "access_token": t},
                                timeout=60))
    link = cevap(requests.get(f"{API}/{yayin['id']}", params={"fields": "permalink", "access_token": t},
                              timeout=30)).get("permalink", "")

    # 4) arşivle + kayıt
    hedef = KOK / "paylasildi"
    hedef.mkdir(exist_ok=True)
    for p in (mp4, mp4.with_suffix(".txt")):
        if p.exists():
            shutil.move(str(p), hedef / p.name)
    KAYIT.parent.mkdir(parents=True, exist_ok=True)
    with open(KAYIT, "a") as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')},{mp4.name},{yayin['id']},{link}\n")
    print(f"Paylaşıldı ✓ {mp4.name} → {link}")
    return link


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kontrol", action="store_true")
    ap.add_argument("--yenile", action="store_true")
    ap.add_argument("--vakit", choices=["sabah", "ogle", "aksam"])
    ap.add_argument("--dosya")
    ap.add_argument("--url", help="videonun herkese açık linki (Instagram buradan indirir)")
    ap.add_argument("--dene", action="store_true", help="işlet ama yayınlama")
    a = ap.parse_args()
    cfg = ayar()
    if a.kontrol:
        return kontrol(cfg)
    if a.yenile:
        return yenile(cfg)
    mp4 = Path(a.dosya) if a.dosya else siradaki(a.vakit)
    if not mp4 or not mp4.exists():
        sys.exit("Sırada video yok. Önce: .venv/bin/python uret.py --adet 30")
    if not a.url:
        sys.exit("Instagram videoyu bir linkten indiriyor: --url gerekli (otomatik paylaşım GitHub'da ci_paylas.py ile).")
    paylas(cfg, mp4, a.url, yayinla=not a.dene)


if __name__ == "__main__":
    main()
