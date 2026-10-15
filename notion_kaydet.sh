#!/bin/bash
# Panodaki Notion anahtarını GitHub secret'ı olarak kaydeder (ekrana yazmadan).
# Çalıştır, sonra 2 dakika içinde Notion'daki API token'ın yanındaki kopyala düğmesine bas.
cd "$(dirname "$0")"
pano() { xsel --clipboard --output 2>/dev/null | tr -d '[:space:]'; }
A=$(pano)
if [[ ! "$A" =~ ^(ntn_|secret_) ]]; then
  echo "Bekliyorum… Notion'da API token'ın yanındaki kopyala düğmesine bas (2 dk)."
  for _ in $(seq 120); do sleep 1; A=$(pano); [[ "$A" =~ ^(ntn_|secret_) ]] && break; done
fi
[[ "$A" =~ ^(ntn_|secret_) ]] || { echo "Notion anahtarı gelmedi, tekrar dene."; exit 1; }
printf %s "$A" | gh secret set NOTION_TOKEN && xsel --clipboard --clear && echo "Kaydedildi ✓ Panodaki anahtar temizlendi."
