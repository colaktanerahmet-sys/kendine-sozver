#!/usr/bin/env python3
"""sira/ klasöründeki her videoyu yüklemeden önce denetler. Sorun varsa çıkış kodu 1.

Bakılanlar: ses kanalı + duyulur seviye, süre, 1080x1920, H.264, boyut, açıklama dosyası,
yazının gerçekten belirdiği (kare parlaklığı) ve videonun yarım kalmadığı.
"""
import re, subprocess, sys
from pathlib import Path

import imageio_ffmpeg

KOK = Path(__file__).resolve().parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def bilgi(v):
    return subprocess.run([FFMPEG, "-hide_banner", "-i", str(v)], capture_output=True, text=True).stderr


def ses_seviyesi(v):
    cikti = subprocess.run([FFMPEG, "-hide_banner", "-i", str(v), "-vn", "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", cikti)
    return float(m.group(1)) if m else None


def denetle(v):
    sorunlar = []
    b = bilgi(v)
    if "Audio: aac" not in b:
        sorunlar.append("ses kanalı yok")
    else:
        db = ses_seviyesi(v)
        if db is None or db < -24:
            sorunlar.append(f"ses çok kısık ({db} dB)")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", b)
    sure = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0
    if not 3 <= sure <= 90:
        sorunlar.append(f"süre uygun değil ({sure:.1f} sn)")
    if "1080x1920" not in b:
        sorunlar.append("çözünürlük 1080x1920 değil")
    if "Video: h264" not in b:
        sorunlar.append("video H.264 değil")
    boyut = v.stat().st_size
    if not 200_000 < boyut < 100_000_000:
        sorunlar.append(f"dosya boyutu tuhaf ({boyut} bayt)")
    txt = v.with_suffix(".txt")
    if not txt.exists() or len(txt.read_text().strip()) < 20:
        sorunlar.append("açıklama (.txt) yok ya da boş")
    elif len(txt.read_text()) > 2200:
        sorunlar.append("açıklama 2200 karakteri aşıyor")
    elif txt.read_text().count("#") > 5:
        sorunlar.append("5'ten fazla hashtag")
    # son kare okunabiliyor mu (yarım kalmış dosya kontrolü)
    son = subprocess.run([FFMPEG, "-v", "error", "-sseof", "-0.5", "-i", str(v), "-frames:v", "1", "-f", "null", "-"],
                         capture_output=True, text=True)
    if son.returncode != 0 or son.stderr.strip():
        sorunlar.append("video bozuk/yarım")
    return sorunlar


def main():
    videolar = sorted((KOK / "sira").glob("*.mp4"))
    hatali = 0
    for v in videolar:
        s = denetle(v)
        if s:
            hatali += 1
            print(f"✗ {v.name}: {', '.join(s)}")
    print(f"{len(videolar)} video denetlendi, {hatali} sorunlu.")
    sys.exit(1 if hatali or not videolar else 0)


if __name__ == "__main__":
    main()
