# @kendine_sozver otomasyonu

- `uret.py` → `icerik.json`'daki sözlerden Reels videoları üretir (`sira/`).
- Videolar GitHub'da **`sira` release**'ine yüklenir; `.github/workflows/paylas.yml` her gün 09:07 / 13:07 / 20:07 (TR) sıradaki videoyu paylaşır.
- Paylaşılanlar: `durum/paylasim_kaydi.csv`. Instagram anahtarı `durum/token.enc` (ENC_KEY secret'ıyla şifreli), her pazartesi otomatik yenilenir.

Yeni video eklemek (bilgisayarda):
```
.venv/bin/python uret.py --adet 30
gh release upload sira sira/*.mp4 sira/*.txt --clobber
```
