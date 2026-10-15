#!/usr/bin/env python3
"""karusel.json'dan kaydırmalı gönderi (carousel) görselleri üretir → karusel/K001_1.jpg … + K001.txt

Kaydırmalı gönderiler en çok KAYDEDİLEN içerik türü; kaydetme de erişimi en çok artıran sinyallerden biri.
Kullanım:
  .venv/bin/python karusel.py              # hepsini üret
  .venv/bin/python karusel.py --id 3       # tek birini (yeniden) üret
Sonra: gh release upload karusel karusel/* --clobber
"""
import argparse, json, random, subprocess, tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from uret import CFG, RENKLER, satirlara_bol

KOK = Path(__file__).resolve().parent
W, H = 1080, 1350  # 4:5, akışta en çok yer kaplayan oran
ALTIN = (255, 226, 160)
ETIKETLER = ["#kendinesözver", "#motivasyon", "#kişiselgelişim", "#motivasyonsözleri", "#farkındalık",
             "#alışkanlık", "#özşefkat", "#disiplin"]


def font(boyut, alt=False):
    return ImageFont.truetype(CFG["font_alt" if alt else "font"], boyut)


def arka_plan(tema, tohum):
    """Tema videosundan bir kare (bulanık + karartılmış); yoksa renk geçişi."""
    videolar = sorted((KOK / "arkaplan" / tema).glob("*.mp4"))
    if videolar:
        video = random.Random(tohum).choice(videolar)
        with tempfile.TemporaryDirectory() as tmp:
            kare = Path(tmp) / "k.jpg"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-ss", "2", "-i", str(video),
                            "-frames:v", "1", str(kare)], check=True)
            img = Image.open(kare).convert("RGB")
        o = W / H
        w, h = img.size
        if w / h > o:
            yeni = int(h * o); img = img.crop(((w - yeni) // 2, 0, (w + yeni) // 2, h))
        else:
            yeni = int(w / o); img = img.crop((0, (h - yeni) // 2, w, (h + yeni) // 2))
        img = img.resize((W, H)).filter(ImageFilter.GaussianBlur(6))
        return ImageEnhance.Brightness(img).enhance(0.5)
    a, b = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in RENKLER[tema])
    img = Image.new("RGB", (W, H))
    ciz = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        ciz.line([(0, y), (W, y)], fill=tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)))
    return img


def ortala(ciz, metin, f, y, genislik, renk, aralik=1.3, en_cok=None):
    satirlar = satirlara_bol(metin, f, genislik, ciz)[:en_cok]
    h = int(f.size * aralik)
    for i, s in enumerate(satirlar):
        ciz.text((W / 2 + 3, y + i * h + 3), s, font=f, fill=(0, 0, 0), anchor="ma")
        ciz.text((W / 2, y + i * h), s, font=f, fill=renk, anchor="ma")
    return y + h * len(satirlar)


def sigdir(ciz, metin, buyuk, kucuk, genislik, en_cok_satir, alt=False):
    for boyut in range(buyuk, kucuk - 1, -4):
        f = font(boyut, alt)
        if len(satirlara_bol(metin, f, genislik, ciz)) <= en_cok_satir:
            return f
    return font(kucuk, alt)


def cerceve(ciz, sayfa, toplam):
    ciz.text((W / 2, 70), CFG["sayfa_adi"], font=font(34, True), fill=(255, 255, 255), anchor="ma")
    ciz.text((W - 60, H - 80), f"{sayfa}/{toplam}", font=font(30, True), fill=(255, 255, 255), anchor="ra")


def kapak(k, toplam):
    img = arka_plan(k["tema"], k["id"])
    ciz = ImageDraw.Draw(img)
    cerceve(ciz, 1, toplam)
    f = sigdir(ciz, k["kapak"], 100, 64, W - 180, 5)
    satir = len(satirlara_bol(k["kapak"], f, W - 180, ciz))
    y = (H - int(f.size * 1.3) * satir) // 2 - 40
    ciz.line([(W / 2 - 50, y - 60), (W / 2 + 50, y - 60)], fill=ALTIN, width=4)
    y = ortala(ciz, k["kapak"], f, y, W - 180, (255, 255, 255))
    # "kaydır" rozeti: ilk karede kaydırmayı tetikler
    metin = "KAYDIR  »"
    fr = font(38, True)
    gen = int(ciz.textlength(metin, font=fr)) + 80
    ciz.rounded_rectangle([(W - gen) / 2, y + 70, (W + gen) / 2, y + 150], radius=40, fill=ALTIN)
    ciz.text((W / 2, y + 110), metin, font=fr, fill=(30, 20, 40), anchor="mm")
    return img


def madde(k, no, baslik, aciklama, toplam):
    img = arka_plan(k["tema"], k["id"])
    ciz = ImageDraw.Draw(img)
    cerceve(ciz, no + 1, toplam)
    fb = sigdir(ciz, baslik, 84, 56, W - 160, 3)
    fa = sigdir(ciz, aciklama, 50, 40, W - 200, 3, alt=True)
    # numara + başlık + açıklama bloğunu dikeyde ortala
    yuk = (250 + int(fb.size * 1.3) * len(satirlara_bol(baslik, fb, W - 160, ciz)) + 90
           + int(fa.size * 1.4) * len(satirlara_bol(aciklama, fa, W - 200, ciz)))
    y0 = (H - yuk) // 2
    ciz.text((W / 2, y0), str(no), font=font(170), fill=ALTIN, anchor="ma")
    y = ortala(ciz, baslik, fb, y0 + 250, W - 160, (255, 255, 255))
    ciz.line([(W / 2 - 40, y + 40), (W / 2 + 40, y + 40)], fill=ALTIN, width=3)
    ortala(ciz, aciklama, fa, y + 90, W - 200, (235, 235, 235), aralik=1.4)
    return img


def kapanis(k, toplam):
    img = arka_plan(k["tema"], k["id"] + 100)
    ciz = ImageDraw.Draw(img)
    cerceve(ciz, toplam, toplam)
    y = ortala(ciz, "Bugün hangisini kendine söz veriyorsun?", font(76), 230, W - 180, (255, 255, 255))
    y = ortala(ciz, "Yoruma numarasını yaz", font(46, True), y + 40, W - 180, ALTIN)
    for i, (bas, alt) in enumerate([("KAYDET", "zor bir anda tekrar bak"),
                                    ("GÖNDER", "ihtiyacı olan birine"),
                                    ("TAKİP ET", "her gün 3 yeni söz")]):
        yy = y + 110 + i * 160
        ciz.rounded_rectangle([140, yy, W - 140, yy + 130], radius=65, outline=ALTIN, width=3)
        ciz.text((W / 2, yy + 46), bas, font=font(40, True), fill=ALTIN, anchor="mm")
        ciz.text((W / 2, yy + 92), alt, font=font(30, True), fill=(235, 235, 235), anchor="mm")
    return img


def aciklama(k):
    r = random.Random(k["id"])
    etiket = " ".join(ETIKETLER[:2] + r.sample(ETIKETLER[2:], 3))
    return (f'{k["kapak"]} 👇\n\n'
            f'Kaydır, hangisi sana iyi geldiyse yoruma numarasını yaz.\n'
            f'📌 Kaydet, zor bir anda tekrar bak.\n'
            f'📩 Bunu duyması gereken birine gönder.\n\n'
            f'Her gün 3 söz: ☀️ sabah · 🌤 öğle · 🌙 akşam\n'
            f'Devamı için {CFG["sayfa_adi"]} takip et.\n\n'
            f'Motivasyon sözleri, kişisel gelişim ve iyi alışkanlıklar için küçük hatırlatmalar.\n\n'
            f'{etiket}')


def uret(k, hedef):
    toplam = len(k["maddeler"]) + 2
    ad = f"K{k['id']:03d}"
    sayfalar = [kapak(k, toplam)]
    sayfalar += [madde(k, i, b, a, toplam) for i, (b, a) in enumerate(k["maddeler"], 1)]
    sayfalar.append(kapanis(k, toplam))
    for i, s in enumerate(sayfalar, 1):
        s.save(hedef / f"{ad}_{i}.jpg", quality=92)  # Instagram karusel API'si yalnızca JPEG kabul ediyor
    (hedef / f"{ad}.txt").write_text(aciklama(k))
    print(f"✓ {ad} ({toplam} sayfa)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int)
    a = ap.parse_args()
    hedef = KOK / "karusel"
    hedef.mkdir(exist_ok=True)
    for k in json.loads((KOK / "karusel.json").read_text()):
        if a.id is None or k["id"] == a.id:
            uret(k, hedef)


if __name__ == "__main__":
    main()
