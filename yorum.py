#!/usr/bin/env python3
"""Son gönderilerdeki yanıtlanmamış yorumlara kısa ve sıcak yanıtlar verir.

Yorumlara hızlı yanıt, gönderinin ilk saatlerinde algoritmaya en güçlü sinyallerden biridir;
ayrıca yorum sayısını ikiye katlar ve takipçiyle bağ kurar.
GitHub Actions'ta her saatlik çalışmada ci_paylas.py tarafından çağrılır.
  python yorum.py --dene   # yanıtları yalnızca yazdırır, göndermez
"""
import datetime, os, random, re, sys, time
from pathlib import Path

import requests

import paylas
from paylas import API, cevap

KOK = Path(__file__).resolve().parent
YANITLANAN = Path(os.environ.get("YANITLANAN", KOK / "durum" / "yanitlanan.txt"))
GUN = 7          # bu kadar günden eski gönderilere bakma
EN_COK = 15      # bir çalışmada en fazla yanıt (spam görünmesin)

SOZ = ["Sözün kayıtlı @{u} 🤝 Bugün kendine verdiğin sözü tutacağına inanıyoruz!",
       "Harika @{u} 🤝 Söz verdin, şimdi sıra küçük bir adımda. Yanındayız!",
       "Bu sözü veren herkesle gurur duyuyoruz @{u} 💛 Akşam nasıl geçtiğini yazmayı unutma!",
       "@{u} sözünü tuttuğun her gün kendine biraz daha güveneceksin 🤝",
       "Söz verildi @{u} ✨ Küçük adımlar, büyük değişimler!"]
NUMARA = ["{n} numara harika bir seçim @{u} 💛 Bugün o sözü tutmanı diliyoruz!",
          "@{u} {n}. madde bizim de favorimiz ✨ Kaydetmeyi unutma!",
          "Güzel seçim @{u} 🤝 {n} numarayı bugün denemeye ne dersin?"]
TESEKKUR = ["Biz teşekkür ederiz @{u} 💛 İyi ki buradasın!",
            "Çok sevindik @{u} 🙏 Her gün yeni bir sözle buradayız.",
            "@{u} beğenmene çok sevindik 💛 İhtiyacı olan biriyle paylaşmayı unutma!",
            "Ne güzel @{u} ✨ Kendine iyi bak!"]
SORU = ["Güzel bir soru @{u} 🙏 Sen olsan nasıl cevaplardın?",
        "@{u} bunu düşünmen bile çok değerli 💛 Biraz kendine zaman ver, cevap gelecektir."]
ZOR = ["@{u} yanındayız 💛 Zor günler de geçer, kendine nazik ol.",
       "Bunu yazdığın için teşekkürler @{u} 🤍 Yalnız değilsin, bir adım bile yeter.",
       "@{u} kendine biraz şefkat göster bugün 💛 Burası her zaman senin için."]
GENEL = ["Yorumun için teşekkürler @{u} 💛 Kendine verdiğin sözleri unutma!",
         "@{u} çok güzel 🤍 Her gün yeni bir hatırlatmayla buradayız.",
         "Teşekkürler @{u} ✨ Bugün kendine hangi sözü veriyorsun?",
         "@{u} 💛 İyi ki buradasın, kendine iyi bak!"]

ATLA = re.compile(r"https?://|www\.|\bdm\b|promo|reklam|takip(e)? ?(et|geri)|f4f|l4l|collab|kazan[çc]", re.I)


def sec(metin, kid, u):
    r = random.Random(kid)
    m = metin.lower()
    if ATLA.search(m):
        return None  # reklam/spam'e yanıt verme
    if re.fullmatch(r"\s*#?([1-9])\s*\.?\s*\W*", m):
        return r.choice(NUMARA).format(n=re.search(r"[1-9]", m).group(), u=u)
    if "söz" in m or re.search(r"\bsoz\b", m):
        return r.choice(SOZ).format(u=u)
    if re.search(r"zor|yorgun|üzgün|kötü|yalnız|bıkt|ağla|mutsuz|depres|kaygı", m):
        return r.choice(ZOR).format(u=u)
    if "?" in m:
        return r.choice(SORU).format(u=u)
    if re.search(r"teşekkür|tesekkur|sağol|sagol|güzel|guzel|harika|süper|muhteşem|amin|❤|💛|🙏|👏|😍|🥰|♥", m) \
            or len(m.strip()) <= 4:
        return r.choice(TESEKKUR).format(u=u)
    return r.choice(GENEL).format(u=u)


def yanitla(cfg, gonder=True):
    t, uid = cfg["ig_access_token"], cfg["ig_user_id"]
    ben = cevap(requests.get(f"{API}/me", params={"fields": "username", "access_token": t}, timeout=30))["username"]
    yapilan = set(YANITLANAN.read_text().split()) if YANITLANAN.exists() else set()
    sinir = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=GUN)
    medya = cevap(requests.get(f"{API}/{uid}/media", timeout=30, params={
        "fields": "id,timestamp,comments_count", "limit": 25, "access_token": t})).get("data", [])
    sayi = 0
    for md in medya:
        if datetime.datetime.fromisoformat(md["timestamp"].replace("+0000", "+00:00")) < sinir:
            continue
        if not md.get("comments_count"):
            continue
        yorumlar = cevap(requests.get(f"{API}/{md['id']}/comments", timeout=30, params={
            "fields": "id,text,username,replies{username}", "limit": 50, "access_token": t})).get("data", [])
        for y in yorumlar:
            u = y.get("username", "")
            if y["id"] in yapilan or u == ben:
                continue
            if any(r.get("username") == ben for r in y.get("replies", {}).get("data", [])):
                yapilan.add(y["id"])
                continue
            mesaj = sec(y.get("text", ""), y["id"], u)
            if mesaj is None:
                yapilan.add(y["id"])
                continue
            print(f"  @{u}: {y.get('text', '')[:60]!r} → {mesaj}")
            if gonder:
                cevap(requests.post(f"{API}/{y['id']}/replies", data={"message": mesaj, "access_token": t},
                                    timeout=30))
                yapilan.add(y["id"])
                time.sleep(random.uniform(4, 9))  # insan gibi aralıklı
            sayi += 1
            if sayi >= EN_COK:
                break
        if sayi >= EN_COK:
            break
    if gonder:
        YANITLANAN.parent.mkdir(exist_ok=True)
        YANITLANAN.write_text("\n".join(sorted(yapilan)) + "\n")
    print(f"Yorum yanıtı: {sayi} {'gönderildi' if gonder else '(deneme, gönderilmedi)'}")


if __name__ == "__main__":
    yanitla(paylas.ayar(), gonder="--dene" not in sys.argv)
