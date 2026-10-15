# @kendine_sozver otomasyonu

- `uret.py` → `icerik.json`'daki sözlerden Reels videoları üretir (`sira/`).
- Videolar GitHub'da **`sira` release**'ine yüklenir; `.github/workflows/paylas.yml` saatte bir bakar; sabah (08:45+), öğle (12:45+), akşam (19:45+ TR) vakti gelmiş ve o gün paylaşılmamışsa sıradaki videoyu Reels + hikâye olarak paylaşır. Zamanlayıcı gecikse/atlasa da bir sonraki saatte telafi edilir.
- Paylaşılanlar: `durum/paylasim_kaydi.csv`. Instagram anahtarı `durum/token.enc` (ENC_KEY secret'ıyla şifreli), her pazartesi otomatik yenilenir.

Yeni video eklemek (bilgisayarda):
```
.venv/bin/python uret.py --adet 30
gh release upload sira sira/*.mp4 sira/*.txt --clobber
```
