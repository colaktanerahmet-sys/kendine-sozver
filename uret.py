#!/usr/bin/env python3
"""icerik.json'daki sözlerden 9:16 Reels videoları üretir → sira/

Kullanım:
  .venv/bin/python uret.py              # sıradaki 6 sözü üret
  .venv/bin/python uret.py --adet 20
  .venv/bin/python uret.py --id 17      # tek bir sözü (yeniden) üret
"""
import argparse, json, math, random, shutil, subprocess, tempfile, wave
from pathlib import Path

import numpy as np
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

KOK = Path(__file__).resolve().parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1080, 1920, 30
CFG = json.loads((KOK / "config.json").read_text())

# Arka plan videosu bulunamazsa kullanılacak renk geçişleri (tema başına)
RENKLER = {
    "dag": ("#1d2b3a", "#5b7a99"), "deniz": ("#06303f", "#2a7f9e"),
    "orman": ("#0f2a1d", "#3f6b4a"), "sehir": ("#120f24", "#3d3566"),
    "yol": ("#2a1f17", "#7a5a3c"), "yagmur": ("#1a2128", "#4e5d6b"),
    "gokyuzu": ("#16324f", "#7fa7c9"), "gunbatimi": ("#2b1030", "#d06a3a"),
    "gundogumu": ("#2d2340", "#e0a15a"), "yildiz": ("#05060f", "#1f2547"),
}

# ---------- büyüme odaklı açıklama ----------
# Instagram'ın en güçlü sinyalleri: DM ile gönderme > kaydetme > yorum > beğeni; izlenme süresi + tekrar izleme.
# Açıklamanın ilk satırı akışta görünen "kanca"; anahtar kelimeler Instagram aramasına (SEO) giriyor.
# Instagram en fazla 5 hashtag'e izin veriyor; 2 sabit + 3 vakte özel.
KANCA = {
    "sabah": ["Güne başlamadan önce bunu oku 👇", "Bu sabah kendine tek bir söz ver 👇",
              "Bugünün görevi basit ama etkili 👇", "Telefonu açtıysan, bunu da okumuş ol 👇",
              "Küçük bir söz, bambaşka bir gün 👇", "Bugün bunu yapanlar yorumda buluşsun 👇"],
    "ogle": ["Günün yarısı geçti. Dur ve bunu oku 👇", "Öğle arası hatırlatması 👇",
             "Yorulduysan, bu senin için 👇", "5 saniyeni ayır, günün geri kalanı değişsin 👇",
             "Günün ikinci yarısını kurtaracak tek cümle 👇"],
    "aksam": ["Uyumadan önce bunu kendine söyle 👇", "Bu gece kendine biraz nazik ol 👇",
              "Zor bir gün geçirdiysen, bunu oku 👇", "Belki de bunu duyman gerekiyordu 👇",
              "Günü kapatmadan önce son bir söz 👇"],
}
GONDER = {
    "sabah": ["Bunu bugün birlikte tutacağın birine gönder 📩", "Sabahları erteleyen o arkadaşına gönder 📩"],
    "ogle": ["Şu an çok yorulan birine gönder 📩", "Mesaide bunaltan birine gönder 📩"],
    "aksam": ["Bu gece bunu duyması gereken birine gönder 📩", "Kendine fazla yüklenen o kişiye gönder 📩"],
}
ETIKET_SABIT = ["#kendinesözver", "#motivasyon"]
ETIKET_VAKIT = {
    "sabah": ["#kişiselgelişim", "#disiplin", "#günaydın", "#alışkanlık", "#motivasyonsözleri"],
    "ogle": ["#kişiselgelişim", "#farkındalık", "#odaklan", "#motivasyonsözleri", "#kendinigeliştir"],
    "aksam": ["#özşefkat", "#iyiolmak", "#iyigeceler", "#huzur", "#güzelsözler"],
}
BASLIK = {"sabah": "Bugün kendine söz ver", "ogle": "Öğlen kendine söz ver", "aksam": "Bu gece kendine söz ver"}
# Videonun son saniyelerinde beliren çağrı (DM paylaşımı ve kaydetme en çok erişim getirir)
VIDEO_CTA = ["İhtiyacı olan birine gönder", "Kaydet · zor bir anda tekrar bak", "Söz veriyorsan yoruma «söz» yaz"]


def gun_no(oge):
    return (oge["id"] - 1) // 3 + 1


def caption(oge):
    r = random.Random(oge["id"])
    v = oge["vakit"]
    etiket = " ".join(ETIKET_SABIT + r.sample(ETIKET_VAKIT[v], 3))
    return (f'{r.choice(KANCA[v])}\n\n'
            f'{BASLIK[v]}: "{oge["soz"]}"\n\n'
            f'🤝 Söz veriyorsan yoruma "söz" yaz.\n'
            f'📌 Kaydet, zor bir anda tekrar bak.\n'
            f'{r.choice(GONDER[v])}\n\n'
            f'Gün {gun_no(oge)} · Her gün 3 söz: ☀️ sabah · 🌤 öğle · 🌙 akşam\n'
            f'Serinin devamını kaçırmamak için {CFG["sayfa_adi"]} takip et.\n\n'
            f'Motivasyon sözleri ve kişisel gelişim için her gün küçük bir hatırlatma.\n\n'
            f'{etiket}')


def sure(soz):
    # yazıyı rahat okuyup sondaki çağrıyı görecek kadar; kısa kalınca video döngüye girer (tekrar izlenme)
    return round(min(12, max(8.5, 5.0 + len(soz.split()) * 0.4)), 1)


# ---------- metin katmanı ----------
def satirlara_bol(metin, font, genislik, ciz):
    satirlar, satir = [], ""
    for kelime in metin.split():
        dene = (satir + " " + kelime).strip()
        if ciz.textlength(dene, font=font) <= genislik:
            satir = dene
        else:
            satirlar.append(satir); satir = kelime
    satirlar.append(satir)
    return satirlar


def aralikli(ciz, xy, metin, font, fill, aralik):
    """Harf aralıklı, ortalanmış başlık."""
    genis = sum(ciz.textlength(c, font=font) for c in metin) + aralik * (len(metin) - 1)
    x = xy[0] - genis / 2
    for c in metin:
        ciz.text((x, xy[1]), c, font=font, fill=fill)
        x += ciz.textlength(c, font=font) + aralik


def metin_png(oge, yol):
    soz = oge["soz"]
    img = karartma_img()
    ciz = ImageDraw.Draw(img)
    for boyut in range(88, 50, -4):
        font = ImageFont.truetype(CFG["font"], boyut)
        satirlar = satirlara_bol(soz, font, W - 180, ciz)
        if len(satirlar) <= 6:
            break
    satir_h = int(boyut * 1.35)
    toplam = satir_h * len(satirlar)
    y0 = (H - toplam) // 2 - 20
    baslik_font = ImageFont.truetype(CFG["font_alt"], 36)
    yb = y0 - 130

    # yumuşak gölge
    golge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gc = ImageDraw.Draw(golge)
    for i, s in enumerate(satirlar):
        gc.text((W / 2, y0 + i * satir_h + 4), s, font=font, fill=(0, 0, 0, 200), anchor="ma")
    aralikli(gc, (W / 2, yb + 3), oge["baslik"], baslik_font, (0, 0, 0, 220), 7)
    golge = golge.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(golge)

    # gün sayacı (seri hissi → takip) + başlık + ayraç + söz
    gun_font = ImageFont.truetype(CFG["font_alt"], 30)
    aralikli(ciz, (W / 2, yb - 60), f"GÜN {gun_no(oge)}", gun_font, (255, 255, 255, 170), 6)
    aralikli(ciz, (W / 2, yb), oge["baslik"], baslik_font, (255, 226, 160, 255), 7)
    ciz.line([(W / 2 - 40, yb + 70), (W / 2 + 40, yb + 70)], fill=(255, 226, 160, 200), width=3)
    for i, s in enumerate(satirlar):
        ciz.text((W / 2, y0 + i * satir_h), s, font=font, fill=(255, 255, 255, 255), anchor="ma")

    # sayfa adı: Reels arayüzünün kapladığı alt bölgenin üstünde kalsın
    kucuk = ImageFont.truetype(CFG["font_alt"], 38)
    ciz.text((W / 2, H - 520), CFG["sayfa_adi"], font=kucuk, fill=(255, 255, 255, 200), anchor="ma")
    img.save(yol)
    return y0 + toplam


def cta_png(oge, yol, y_alt):
    """Son saniyelerde beliren paylaşım çağrısı."""
    metin = VIDEO_CTA[oge["id"] % len(VIDEO_CTA)]
    font = ImageFont.truetype(CFG["font_alt"], 40)
    gen = int(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(metin, font=font)) + 68
    img = Image.new("RGBA", (gen, 80), (0, 0, 0, 0))
    ciz = ImageDraw.Draw(img)
    ciz.rounded_rectangle([0, 0, gen - 1, 79], radius=40, fill=(255, 226, 160, 235))
    ciz.text((gen / 2, 40), metin, font=font, fill=(30, 20, 40, 255), anchor="mm")
    img.save(yol)
    return (W - gen) // 2, y_alt + 52


# ---------- müzik ----------
def sentez_muzik(yol, sn, tohum):
    """Telif derdi olmayan, sakin bir ambient pad üretir."""
    r = random.Random(tohum)
    sr = 44100
    kok = r.choice([220.0, 196.0, 233.08, 207.65])
    ilerleyis = r.choice([[0, 8, 3, 10], [0, 5, 9, 7], [0, 3, 8, 7], [0, 10, 8, 5]])
    akor = [0, 4, 7, 12] if r.random() < .5 else [0, 3, 7, 12]
    t = np.arange(int(sr * sn)) / sr
    ses = np.zeros_like(t)
    parca = sn / len(ilerleyis)
    for i, yari in enumerate(ilerleyis):
        bas, son = i * parca, (i + 1) * parca + 1.2
        maske = (t >= bas) & (t < son)
        tt = t[maske] - bas
        zarf = np.minimum(1, tt / 1.0) * np.minimum(1, np.maximum(0, (son - bas - tt) / 1.2))
        for a in akor:
            f = kok * 2 ** ((yari + a) / 12)
            for h, g in ((1, 1), (2, .25), (3, .08)):
                ses[maske] += g * zarf * np.sin(2 * np.pi * f * h * tt + 0.3 * np.sin(2 * np.pi * .2 * tt))
        f_bas = kok / 2 * 2 ** (yari / 12)
        ses[maske] += .6 * zarf * np.sin(2 * np.pi * f_bas * tt)
    ses = np.convolve(ses, np.ones(12) / 12, mode="same")
    ses *= 0.25 / (np.max(np.abs(ses)) + 1e-9)
    stereo = np.stack([ses, np.roll(ses, 300)], axis=1)
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())


def muzik_sec(oge, sn, gecici):
    dosyalar = sorted(p for p in (KOK / "muzik").glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg"))
    if dosyalar:
        return random.Random(oge["id"]).choice(dosyalar)
    yol = Path(gecici) / "muzik.wav"
    sentez_muzik(yol, sn + 1, oge["id"])
    return yol


# ---------- arka plan ----------
YEDEK_TEMA = {"gundogumu": ["gunbatimi", "gokyuzu", "dag"], "yildiz": ["sehir", "gunbatimi", "deniz"],
              "gokyuzu": ["dag", "deniz"], "gunbatimi": ["deniz", "gokyuzu"], "yagmur": ["sehir", "orman"]}


def arkaplan_sec(oge):
    """Temanın videosu yoksa benzer temaya, o da yoksa herhangi bir videoya düşer; renk geçişi son çare."""
    for tema in [oge["tema"], *YEDEK_TEMA.get(oge["tema"], []), "*"]:
        videolar = sorted((KOK / "arkaplan").glob(f"{tema}/*.mp4"))
        if videolar:
            return random.Random(oge["id"] * 7).choice(videolar)
    return None


def gradyan_png(tema, yol):
    a, b = (np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)]) for c in RENKLER.get(tema, RENKLER["gokyuzu"]))
    hh = H + 600
    k = np.linspace(0, 1, hh)[:, None, None]
    dalga = 0.08 * np.sin(np.linspace(0, 3 * math.pi, W))[None, :, None]
    dizi = np.clip(a + (b - a) * np.clip(k + dalga, 0, 1), 0, 255).astype(np.uint8)
    Image.fromarray(dizi).save(yol)


def karartma_img():
    """Yazının durduğu orta bölgeyi yumuşakça koyulaştıran katman (hareketli arka planda okunurluk)."""
    y = np.arange(H)[:, None]
    alfa = 0.15 + 0.45 * np.exp(-(((y - (H / 2 - 120)) / 520) ** 2))
    dizi = np.zeros((H, W, 4), np.uint8)
    dizi[..., 3] = np.broadcast_to((alfa * 255).astype(np.uint8), (H, W))
    return Image.fromarray(dizi, "RGBA")


# ---------- birleştirme ----------
def uret(oge, hedef):
    sn = sure(oge["soz"])
    with tempfile.TemporaryDirectory() as g:
        png = Path(g) / "metin.png"
        y_alt = metin_png(oge, png)
        cp = Path(g) / "cta.png"
        cx, cy = cta_png(oge, cp, y_alt)
        muzik = muzik_sec(oge, sn, g)
        bg = arkaplan_sec(oge)
        if bg:
            girdi = ["-stream_loop", "-1", "-i", str(bg)]
            vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                  f"fps={FPS},eq=brightness=-0.12:saturation=0.85[bg]")
        else:
            gp = Path(g) / "grad.png"
            gradyan_png(oge["tema"], gp)
            girdi = ["-loop", "1", "-framerate", str(FPS), "-i", str(gp)]
            vf = f"[0:v]crop={W}:{H}:0:'600*t/{sn}'[bg]"
        # yazı hızlı belirir (ilk saniye kaydırmayı durdurmalı); çağrı son 3 saniyede gelir
        filtre = (vf + f";[1:v]format=rgba,fade=t=in:st=0.1:d=0.5:alpha=1[t];"
                  f"[3:v]format=rgba,fade=t=in:st={sn - 3}:d=0.5:alpha=1[c];"
                  f"[bg][t]overlay=0:0[bgt];[bgt][c]overlay={cx}:{cy},format=yuv420p[v];"
                  f"[2:a]atrim=0:{sn},afade=t=in:d=0.8,afade=t=out:st={sn - 1.2}:d=1.2,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        komut = [FFMPEG, "-y", "-loglevel", "error", "-threads", "2", "-filter_complex_threads", "2", *girdi,
                 "-loop", "1", "-framerate", str(FPS), "-i", str(png),
                 "-stream_loop", "-1", "-i", str(muzik),
                 "-loop", "1", "-framerate", str(FPS), "-i", str(cp),
                 "-filter_complex", filtre, "-map", "[v]", "-map", "[a]", "-t", str(sn),
                 "-c:v", "libx264", "-preset", "medium", "-x264-params", "rc-lookahead=10:threads=2", "-crf", "21", "-maxrate", "2500k", "-bufsize", "5000k", "-r", str(FPS),
                 "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(Path(g) / "cikti.mp4")]
        subprocess.run(komut, check=True)
        # yalnızca tamamlanmış video sıraya girer (yarım dosya asla kalmaz)
        shutil.move(str(Path(g) / "cikti.mp4"), str(hedef))
    hedef.with_suffix(".txt").write_text(caption(oge))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adet", type=int, default=6)
    ap.add_argument("--id", type=int)
    a = ap.parse_args()
    icerik = json.loads((KOK / "icerik.json").read_text())
    yapilmis = {int(p.stem.split("_")[0]) for d in ("sira", "paylasildi") for p in (KOK / d).glob("*.mp4")}
    if a.id:
        secim = [o for o in icerik if o["id"] == a.id]
    else:
        secim = [o for o in icerik if o["id"] not in yapilmis][: a.adet]
    if not secim:
        print("Üretilecek söz kalmadı. icerik.json'a yeni söz ekle."); return
    for o in secim:
        hedef = KOK / "sira" / f'{o["id"]:03d}_{o["tema"]}.mp4'
        print(f"→ {hedef.name}  ({sure(o['soz'])} sn)  {o['soz']}")
        uret(o, hedef)
    print(f"Tamam. sira/ klasöründe {len(list((KOK / 'sira').glob('*.mp4')))} video bekliyor.")


if __name__ == "__main__":
    main()
