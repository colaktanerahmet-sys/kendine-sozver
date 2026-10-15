#!/usr/bin/env python3
"""Haftalık Instagram istatistik raporu → GitHub Issue (sahibine bildirim + e-posta gider).

Her pazartesi ci_paylas.py yenile adımından sonra çalışır; elle: ci_paylas.py rapor [--dene]
Takipçi sayısı her hafta durum/istatistik.csv'ye yazılır, haftalık değişim buradan hesaplanır.
"""
import datetime, json, os, subprocess, sys
from collections import defaultdict
from pathlib import Path

import requests

import paylas
from paylas import API, cevap

KOK = Path(__file__).resolve().parent
GECMIS = KOK / "durum" / "istatistik.csv"
TR = datetime.timezone(datetime.timedelta(hours=3))
VAKIT_AD = {"sabah": "☀️ Sabah", "ogle": "🌤 Öğle", "aksam": "🌙 Akşam", "karusel": "🗂 Kaydırmalı"}
METRIK = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions"]


def get(yol, **p):
    p["access_token"] = os.environ.get("IG_ACCESS_TOKEN") or paylas.ayar()["ig_access_token"]
    return cevap(requests.get(f"{API}/{yol}", params=p, timeout=30))


def medya_istatistik(m):
    """Önce ayrıntılı içgörüler (görüntülenme, erişim, kaydetme, paylaşım); izin yoksa beğeni+yorum."""
    s = {"likes": m.get("like_count", 0), "comments": m.get("comments_count", 0)}
    for metrikler in (METRIK, [x for x in METRIK if x != "views"]):
        try:
            for d in get(f"{m['id']}/insights", metric=",".join(metrikler)).get("data", []):
                s[d["name"]] = d["values"][0]["value"] if d.get("values") else d.get("total_value", {}).get("value", 0)
            s["_icgoru"] = True
            break
        except RuntimeError as e:
            s["_hata"] = str(e)
    s.setdefault("total_interactions", s["likes"] + s["comments"] + s.get("shares", 0) + s.get("saved", 0))
    return s


def tur(m, icerik):
    if m.get("media_type") == "CAROUSEL_ALBUM":
        return "karusel"
    satir = (m.get("caption") or "").lower()
    for o in icerik.values():  # açıklamadaki söz cümlesinden vakti bul
        if o["soz"].lower() in satir:
            return o["vakit"]
    return "?"


def sayi(x):
    return f"{x:,}".replace(",", ".") if isinstance(x, int) else str(x)


def stok():
    import ci_paylas
    try:
        yapilan = ci_paylas.paylasilanlar()
        icerik = {o["id"]: o for o in json.loads((KOK / "icerik.json").read_text())}
        videolar = ci_paylas.gh("release", "view", "sira", "--json", "assets", "-q", ".assets[].name").split()
        kalan = defaultdict(int)
        for v in videolar:
            if v.endswith(".mp4") and v not in yapilan:
                kalan[ci_paylas.vakit_of(icerik, v)] += 1
        kar = ci_paylas.gh("release", "view", "karusel", "--json", "assets", "-q", ".assets[].name").split()
        kalan["karusel"] = len({a.split("_")[0].split(".")[0] for a in kar} - yapilan)
        return kalan
    except Exception as e:
        print(f"::warning::Stok okunamadı: {e}")
        return {}


def rapor(cfg):
    uid = cfg["ig_user_id"]
    icerik = {o["id"]: o for o in json.loads((KOK / "icerik.json").read_text())}
    simdi = datetime.datetime.now(TR)
    bas = simdi - datetime.timedelta(days=7)
    hesap = get(uid, fields="username,followers_count,media_count")

    # takipçi geçmişi
    onceki = None
    if GECMIS.exists():
        satirlar = [s.split(",") for s in GECMIS.read_text().splitlines() if s and not s.startswith("tarih")]
        if satirlar:
            onceki = int(satirlar[-1][1])
    GECMIS.parent.mkdir(exist_ok=True)
    if not GECMIS.exists():
        GECMIS.write_text("tarih,takipci,gonderi\n")
    with open(GECMIS, "a") as f:
        f.write(f"{simdi.date()},{hesap['followers_count']},{hesap['media_count']}\n")

    # hesap geneli (izin varsa)
    hesap_ic = {}
    try:
        veri = get(f"{uid}/insights", metric="reach,views,accounts_engaged,total_interactions,follows_and_unfollows",
                   period="day", metric_type="total_value", since=int(bas.timestamp()), until=int(simdi.timestamp()))
        hesap_ic = {d["name"]: d.get("total_value", {}).get("value", 0) for d in veri.get("data", [])}
    except RuntimeError as e:
        print(f"::warning::Hesap içgörüleri alınamadı: {e}")

    medya = get(f"{uid}/media", fields="id,caption,media_type,timestamp,permalink,like_count,comments_count",
                limit=50).get("data", [])
    hafta = []
    for m in medya:
        t = datetime.datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00"))
        if t >= bas:
            hafta.append((m, tur(m, icerik), medya_istatistik(m)))
    icgoru_var = any(s.get("_icgoru") for _, _, s in hafta)

    # --- metin ---
    fark = "" if onceki is None else f" ({'+' if hesap['followers_count'] - onceki >= 0 else ''}{hesap['followers_count'] - onceki} bu hafta)"
    toplam = lambda k: sum(s.get(k, 0) or 0 for _, _, s in hafta)
    L = [f"## @{hesap['username']} · {bas:%d.%m} – {simdi:%d.%m.%Y} haftalık rapor", "",
         "| | |", "|---|---|",
         f"| 👥 Takipçi | **{sayi(hesap['followers_count'])}**{fark} |",
         f"| 📤 Bu hafta paylaşılan | {len(hafta)} gönderi |"]
    if icgoru_var:
        L += [f"| 👁 Görüntülenme | {sayi(toplam('views'))} |", f"| 📡 Erişim (gönderi toplamı) | {sayi(toplam('reach'))} |"]
    L += [f"| ❤️ Beğeni | {sayi(toplam('likes'))} |", f"| 💬 Yorum | {sayi(toplam('comments'))} |"]
    if icgoru_var:
        L += [f"| 📌 Kaydetme | {sayi(toplam('saved'))} |", f"| 📩 Paylaşım (gönder) | {sayi(toplam('shares'))} |"]
    if hesap_ic:
        L += [f"| 🙋 Etkileşen hesap | {sayi(hesap_ic.get('accounts_engaged', 0))} |"]
    L.append("")

    if hafta:
        sirali = sorted(hafta, key=lambda x: x[2].get("total_interactions", 0), reverse=True)
        L += ["### 🏆 En iyi 3 gönderi", ""]
        for i, (m, tr_, s) in enumerate(sirali[:3], 1):
            ilk = next((x for x in (m.get("caption") or "").splitlines() if x.strip()), "")[:70]
            ek = f" · 👁 {sayi(s.get('views', s.get('reach', 0)))}" if icgoru_var else ""
            L.append(f"{i}. [{ilk}]({m['permalink']}) — {VAKIT_AD.get(tr_, tr_)} · "
                     f"etkileşim {s.get('total_interactions', 0)}{ek}")
        L.append("")

        gruplar = defaultdict(list)
        for m, tr_, s in hafta:
            gruplar[tr_].append(s)
        anahtar = "views" if icgoru_var else "total_interactions"
        L += ["### ⏰ Vakit / tür karşılaştırması (gönderi başına ortalama)", "",
              f"| | Gönderi | {'Görüntülenme' if icgoru_var else 'Etkileşim'} | Etkileşim |", "|---|---|---|---|"]
        ort = {}
        for tr_, ss in sorted(gruplar.items(), key=lambda x: -len(x[1])):
            ort[tr_] = sum(s.get(anahtar, 0) or 0 for s in ss) / len(ss)
            L.append(f"| {VAKIT_AD.get(tr_, tr_)} | {len(ss)} | {ort[tr_]:.0f} | "
                     f"{sum(s.get('total_interactions', 0) for s in ss) / len(ss):.1f} |")
        L.append("")

        # basit öneriler
        L += ["### 💡 Bu haftanın önerileri", ""]
        if len(ort) > 1:
            en = max(ort, key=ort.get)
            L.append(f"- En iyi giden: **{VAKIT_AD.get(en, en)}**. Benzer içerikleri artırmayı düşünebiliriz.")
        if icgoru_var and toplam("views"):
            kay = toplam("saved") / max(toplam("reach") or toplam("views"), 1) * 100
            L.append(f"- Kaydetme oranı %{kay:.1f}. "
                     + ("Çok iyi, kaydedilen içerik daha çok öne çıkarılır." if kay >= 2 else
                        "Artırmak için kaydırmalı gönderiler ve \"kaydet\" çağrıları önemli."))
        if toplam("comments") < len(hafta):
            L.append("- Yorum az: birkaç Reels'e uygulamadan popüler müzik eklemek ve benzer sayfalarda yorum yapmak erişimi artırır.")
        L.append("")
    else:
        L += ["Bu hafta paylaşım yok — otomasyonu kontrol et.", ""]

    k = stok()
    if k:
        L += ["### 📦 İçerik stoğu", "",
              f"Kalan video: sabah {k.get('sabah', 0)} · öğle {k.get('ogle', 0)} · akşam {k.get('aksam', 0)} · "
              f"kaydırmalı {k.get('karusel', 0)}"]
        az = min(k.get("sabah", 0), k.get("ogle", 0), k.get("aksam", 0))
        if az <= 14 or k.get("karusel", 0) <= 6:
            L.append("\n⚠️ **Stok azalıyor** — Claude'a \"yeni içerik üret\" demen yeterli.")
        L.append("")
    if not icgoru_var and hafta:
        L += ["<sub>Not: Görüntülenme/kaydetme/paylaşım verileri için uygulamada *instagram_business_manage_insights* "
              f"izni gerekiyor. ({hafta[0][2].get('_hata', '')[:120]})</sub>", ""]
    L.append(f"<sub>Otomatik rapor · @{os.environ.get('GITHUB_REPOSITORY_OWNER', '')}</sub>")
    return f"📊 Haftalık rapor {simdi:%d.%m.%Y} · {sayi(hesap['followers_count'])} takipçi", "\n".join(L)


def main(cfg, gonder=True):
    baslik, govde = rapor(cfg)
    print(baslik); print(govde)
    if gonder:
        subprocess.run(["gh", "issue", "create", "--title", baslik, "--body", govde, "--label", "rapor"],
                       check=True)
        print("Rapor GitHub Issue olarak açıldı ✓")


if __name__ == "__main__":
    main(paylas.ayar(), gonder="--dene" not in sys.argv)
