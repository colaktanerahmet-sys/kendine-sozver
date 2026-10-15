#!/usr/bin/env python3
"""icerik.json'daki sözlerden 9:16 Reels videoları üretir → sira/

Kullanım:
  .venv/bin/python uret.py              # sıradaki 6 sözü üret
  .venv/bin/python uret.py --adet 20
  .venv/bin/python uret.py --id 17      # tek bir sözü (yeniden) üret
"""
import argparse, asyncio, json, math, random, shutil, subprocess, tempfile, wave
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


# ---------- seslendirme (izlenme süresini en çok artıran şey: ses + senkron yazı) ----------
SES = "tr-TR-EmelNeural"
SES_BASLIK = {"sabah": "Bugün kendine bir söz ver.", "ogle": "Öğlen kendine bir söz ver.",
              "aksam": "Bu gece kendine bir söz ver."}
SES_CTA = ["Bunu ihtiyacı olan birine gönder.", "Kaydet, zor bir anda tekrar bak.", "Söz veriyorsan, yoruma söz yaz."]


def seslendir(metin, yol):
    """Microsoft Edge nöral sesi ile okur → mp3 + kelime zamanları [(kelime, başlangıç, süre)]."""
    import edge_tts

    async def calis():
        kelimeler = []
        with open(yol, "wb") as f:
            async for c in edge_tts.Communicate(metin, SES, rate="-4%", boundary="WordBoundary").stream():
                if c["type"] == "audio":
                    f.write(c["data"])
                elif c["type"] == "WordBoundary":
                    kelimeler.append((c["text"], c["offset"] / 1e7, c["duration"] / 1e7))
        return kelimeler

    for deneme in range(4):
        try:
            return asyncio.run(calis())
        except Exception:
            if deneme == 3:
                raise
            import time; time.sleep(3 * (deneme + 1))


def ses_suresi(yol):
    r = subprocess.run([FFMPEG, "-i", str(yol), "-f", "null", "-"], capture_output=True, text=True)
    t = [x for x in r.stderr.split("time=")[1:]][-1].split()[0]
    sa, dk, sn = t.split(":")
    return int(sa) * 3600 + int(dk) * 60 + float(sn)


def kelime_kareleri(oge, g, soz_zaman, t_soz):
    """Sözün kelimeleri okunurken tek tek belirir, okunan kelime altın rengi.
    Her kare tam ekran RGBA PNG; ffconcat ile süreleriyle sıralanır."""
    soz = oge["soz"]
    olcu = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for boyut in range(88, 50, -4):
        font = ImageFont.truetype(CFG["font"], boyut)
        satirlar = satirlara_bol(soz, font, W - 180, olcu)
        if len(satirlar) <= 6:
            break
    satir_h = int(boyut * 1.35)
    y0 = (H - satir_h * len(satirlar)) // 2 - 20
    # kelime konumları (satır ortalı, düzen kareler arasında sabit → zıplama yok)
    konum = []
    bosluk = olcu.textlength(" ", font=font)
    for i, s in enumerate(satirlar):
        x = W / 2 - olcu.textlength(s, font=font) / 2
        for k in s.split():
            konum.append((k, x, y0 + i * satir_h))
            x += olcu.textlength(k, font=font) + bosluk
    n = len(konum)
    # kelime başına başlangıç zamanı: TTS sınırları kelime sayısıyla uyuşmazsa eşit dağıt
    if len(soz_zaman) == n:
        basla = [t_soz + z[1] for z in soz_zaman]
    else:
        toplam = (soz_zaman[-1][1] + soz_zaman[-1][2]) if soz_zaman else 0.35 * n
        basla = [t_soz + toplam * i / n for i in range(n)]

    # söz ilk karede soluk görünür (kaydıran kişi anında okur), okundukça kelimeler parlar
    taban = metin_png_taban(oge, satirlar, y0)
    golge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gc = ImageDraw.Draw(golge)
    for k_, x, y in konum:
        gc.text((x, y + 4), k_, font=font, fill=(0, 0, 0, 200))
    taban.alpha_composite(golge.filter(ImageFilter.GaussianBlur(10)))
    altin, beyaz, soluk = (255, 226, 160, 255), (255, 255, 255, 255), (255, 255, 255, 105)
    kareler = []
    for k in range(n + 1):
        img = taban.copy()
        ciz = ImageDraw.Draw(img)
        for j, (k_, x, y) in enumerate(konum):
            renk = soluk if j >= k else (altin if j == k - 1 and k < n else beyaz)
            ciz.text((x, y), k_, font=font, fill=renk)
        yol = Path(g) / f"k{k:02d}.png"
        img.save(yol)
        kareler.append(yol)
    zamanlar = [0.0] + basla
    satir = ["ffconcat version 1.0"]
    for k, yol in enumerate(kareler):
        bitis = zamanlar[k + 1] if k + 1 < len(zamanlar) else None
        satir.append(f"file '{yol}'")
        if bitis is not None:
            satir.append(f"duration {max(0.04, bitis - zamanlar[k]):.3f}")
    satir.append(f"file '{kareler[-1]}'")  # son kare bitişe kadar kalsın
    liste = Path(g) / "kareler.txt"
    liste.write_text("\n".join(satir) + "\n")
    return liste, y0 + satir_h * len(satirlar)


def metin_png_taban(oge, satirlar, y0):
    """Karartma + gün sayacı + başlık + sayfa adı (sözün kendisi hariç)."""
    img = karartma_img()
    ciz = ImageDraw.Draw(img)
    baslik_font = ImageFont.truetype(CFG["font_alt"], 36)
    yb = y0 - 130
    golge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    aralikli(ImageDraw.Draw(golge), (W / 2, yb + 3), oge["baslik"], baslik_font, (0, 0, 0, 220), 7)
    img.alpha_composite(golge.filter(ImageFilter.GaussianBlur(10)))
    gun_font = ImageFont.truetype(CFG["font_alt"], 30)
    aralikli(ciz, (W / 2, yb - 60), f"GÜN {gun_no(oge)}", gun_font, (255, 255, 255, 170), 6)
    aralikli(ciz, (W / 2, yb), oge["baslik"], baslik_font, (255, 226, 160, 255), 7)
    ciz.line([(W / 2 - 40, yb + 70), (W / 2 + 40, yb + 70)], fill=(255, 226, 160, 200), width=3)
    kucuk = ImageFont.truetype(CFG["font_alt"], 38)
    ciz.text((W / 2, H - 520), CFG["sayfa_adi"], font=kucuk, fill=(255, 255, 255, 200), anchor="ma")
    return img


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
    if CFG.get("seslendirme", False):  # config.json "seslendirme": true ile açılır
        return uret_sesli(oge, hedef)
    return uret_sessiz(oge, hedef)


def arkaplan_girdisi(oge, g, sn):
    bg = arkaplan_sec(oge)
    if bg:
        return (["-stream_loop", "-1", "-i", str(bg)],
                f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"fps={FPS},eq=brightness=-0.12:saturation=0.85[bg]")
    gp = Path(g) / "grad.png"
    gradyan_png(oge["tema"], gp)
    return ["-loop", "1", "-framerate", str(FPS), "-i", str(gp)], f"[0:v]crop={W}:{H}:0:'600*t/{sn}'[bg]"


def uret_sesli(oge, hedef):
    with tempfile.TemporaryDirectory() as g:
        g = Path(g)
        cta_i = oge["id"] % len(VIDEO_CTA)
        seslendir(SES_BASLIK[oge["vakit"]], g / "s1.mp3")
        soz_zaman = seslendir(oge["soz"], g / "s2.mp3")
        seslendir(SES_CTA[cta_i], g / "s3.mp3")
        d1, d2, d3 = (ses_suresi(g / f"s{i}.mp3") for i in (1, 2, 3))
        t_soz = 0.15 + d1 + 0.3
        t_cta = t_soz + d2 + 0.7
        sn = round(t_cta + d3 + 0.9, 2)

        liste, y_alt = kelime_kareleri(oge, g, soz_zaman, t_soz)
        cp = g / "cta.png"
        cx, cy = cta_png(oge, cp, y_alt)
        muzik = muzik_sec(oge, sn, g)
        girdi, vf = arkaplan_girdisi(oge, g, sn)
        ms = lambda t: int(t * 1000)
        filtre = (vf + ";[1:v]fps=30,format=rgba[t];"
                  f"[3:v]format=rgba,fade=t=in:st={t_cta - 0.1:.2f}:d=0.4:alpha=1[c];"
                  "[bg][t]overlay=0:0[bgt];[bgt][c]overlay=" f"{cx}:{cy},format=yuv420p[v];"
                  # ses: başlık / söz / çağrı doğru anlara; müzik sesin altında kısık
                  f"[4:a]adelay={ms(0.15)}|{ms(0.15)}[a1];[5:a]adelay={ms(t_soz)}|{ms(t_soz)}[a2];"
                  f"[6:a]adelay={ms(t_cta)}|{ms(t_cta)}[a3];"
                  "[a1][a2][a3]amix=inputs=3:normalize=0,volume=1.6[ses];"
                  f"[2:a]atrim=0:{sn},volume=0.22,afade=t=in:d=0.6,afade=t=out:st={sn - 1.0}:d=1.0[m];"
                  f"[ses][m]amix=inputs=2:normalize=0:duration=longest,atrim=0:{sn},"
                  "loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        komut = [FFMPEG, "-y", "-loglevel", "error", "-threads", "2", "-filter_complex_threads", "2", *girdi,
                 "-f", "concat", "-safe", "0", "-i", str(liste),
                 "-stream_loop", "-1", "-i", str(muzik),
                 "-loop", "1", "-framerate", str(FPS), "-i", str(cp),
                 "-i", str(g / "s1.mp3"), "-i", str(g / "s2.mp3"), "-i", str(g / "s3.mp3"),
                 "-filter_complex", filtre, "-map", "[v]", "-map", "[a]", "-t", str(sn),
                 "-c:v", "libx264", "-preset", "medium", "-x264-params", "rc-lookahead=10:threads=2", "-crf", "21",
                 "-maxrate", "2500k", "-bufsize", "5000k", "-r", str(FPS),
                 "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(g / "cikti.mp4")]
        subprocess.run(komut, check=True)
        shutil.move(str(g / "cikti.mp4"), str(hedef))
    hedef.with_suffix(".txt").write_text(caption(oge))


def uret_sessiz(oge, hedef):
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
