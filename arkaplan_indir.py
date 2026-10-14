#!/usr/bin/env python3
"""Pixabay'den (ücretsiz, ticari kullanıma açık lisans) arka plan videoları indirir.

API anahtarını config.json → "pixabay_api_key" alanına yaz
(pixabay.com'a üye ol → https://pixabay.com/api/docs/ sayfasında "key" yazan yer).
Yatay videolar uret.py'de ortadan 9:16 kırpılır.
Kullanım:  .venv/bin/python arkaplan_indir.py [--adet 8]
"""
import argparse, json
from pathlib import Path

import requests

KOK = Path(__file__).resolve().parent
ARAMA = {
    "dag": "mountains", "deniz": "ocean waves", "orman": "forest",
    "sehir": "city night", "yol": "road", "yagmur": "rain",
    "gokyuzu": "clouds timelapse", "gunbatimi": "sunset", "gundogumu": "sunrise",
    "yildiz": "night sky stars",
}


def en_uygun_dosya(video):
    """1080p civarını tercih et; 4K gereksiz büyük, 720 altı bulanık."""
    adaylar = [v for v in video["videos"].values()
               if v.get("url") and min(v.get("width", 0), v.get("height", 0)) >= 1080
               and 0 < v.get("size", 0) <= 25_000_000]   # yavaş bağlantıda dev dosyalardan kaçın
    if not adaylar:
        return None
    return min(adaylar, key=lambda v: v["size"])["url"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adet", type=int, default=8)
    a = ap.parse_args()
    anahtar = json.loads((KOK / "config.json").read_text()).get("pixabay_api_key")
    if not anahtar:
        raise SystemExit("config.json içine pixabay_api_key ekle (https://pixabay.com/api/docs/ → ücretsiz).")
    for tema, sorgu in ARAMA.items():
        klasor = KOK / "arkaplan" / tema
        klasor.mkdir(parents=True, exist_ok=True)
        mevcut = len(list(klasor.glob("*.mp4")))
        if mevcut >= a.adet:
            print(f"{tema}: {mevcut} video zaten var"); continue
        r = requests.get("https://pixabay.com/api/videos/", timeout=30,
                         params={"key": anahtar, "q": sorgu, "per_page": 50,
                                 "safesearch": "true", "order": "popular"})
        r.raise_for_status()
        for v in r.json()["hits"]:
            if mevcut >= a.adet:
                break
            hedef = klasor / f'pixabay_{v["id"]}.mp4'
            link = en_uygun_dosya(v)
            if hedef.exists() or not link or v.get("duration", 0) < 6:
                continue
            with requests.get(link, stream=True, timeout=120) as d:
                d.raise_for_status()
                gecici = hedef.with_suffix(".part")
                with open(gecici, "wb") as f:
                    for parca in d.iter_content(1 << 20):
                        f.write(parca)
                gecici.rename(hedef)
            mevcut += 1
            print(f"{tema}: {hedef.name}")
    print("Bitti.")


if __name__ == "__main__":
    main()
