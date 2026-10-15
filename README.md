# @kendine_sozver otomasyonu

- `uret.py` → `icerik.json`'daki sözlerden Reels videoları üretir (`sira/`).
- Videolar GitHub'da **`sira` release**'ine yüklenir; `.github/workflows/paylas.yml` saatte bir bakar; sabah (08:45+), öğle (12:45+), akşam (19:45+ TR) vakti gelmiş ve o gün paylaşılmamışsa sıradaki videoyu Reels + hikâye olarak paylaşır. Zamanlayıcı gecikse/atlasa da bir sonraki saatte telafi edilir.
- Paylaşılanlar: `durum/paylasim_kaydi.csv`. Instagram anahtarı `durum/token.enc` (ENC_KEY secret'ıyla şifreli), her pazartesi otomatik yenilenir.

- Kaydırmalı gönderiler: `karusel.py` → **`karusel` release**; salı/perşembe/cumartesi 16:45+ TR paylaşılır.
- Her saatlik çalışmada `yorum.py` son 7 günün yanıtlanmamış yorumlarına kısa yanıt verir (`durum/yanitlanan.txt`).

- Her pazartesi ~06:30 TR `rapor.py` haftalık istatistik raporunu Notion'daki "Kendine Söz Ver · Haftalık Raporlar" sayfasına (NOTION_TOKEN secret + NOTION_PAGE_ID variable) ve GitHub Issue olarak ekler.

Yeni video eklemek (bilgisayarda):
```
.venv/bin/python uret.py --adet 30
gh release upload sira sira/*.mp4 sira/*.txt --clobber
```
