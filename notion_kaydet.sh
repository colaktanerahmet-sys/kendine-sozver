#!/bin/bash
# Panodaki Notion entegrasyon anahtarını GitHub secret'ı olarak kaydeder (ekrana yazmadan).
# notion.so/my-integrations → entegrasyon → "Internal Integration Secret" → Copy, sonra: ./notion_kaydet.sh
cd "$(dirname "$0")"
A=$(xsel --clipboard --output | tr -d '[:space:]')
case "$A" in ntn_*|secret_*) ;; *) echo "Panoda Notion anahtarı yok (ntn_ ile başlamalı). 'Copy'ye basıp tekrar dene."; exit 1;; esac
printf %s "$A" | gh secret set NOTION_TOKEN && xsel --clipboard --clear && echo "Kaydedildi ✓ Panodaki anahtar temizlendi."
