#!/usr/bin/env python3
"""Panodaki Instagram erişim anahtarını config.json'a kaydeder (ekrana yazmadan).

Meta'daki "Token generated" penceresinde Copy'ye bas, sonra:
  .venv/bin/python anahtar_kaydet.py
"""
import json, subprocess, sys
from pathlib import Path

import requests

KOK = Path(__file__).resolve().parent
anahtar = subprocess.run(["xsel", "--clipboard", "--output"], capture_output=True, text=True).stdout.strip()
if not anahtar.startswith("IG") or len(anahtar) < 50:
    sys.exit("Panoda Instagram anahtarı yok. Meta penceresindeki 'Copy' düğmesine basıp tekrar dene.")

r = requests.get("https://graph.instagram.com/v23.0/me",
                 params={"fields": "user_id,username,account_type", "access_token": anahtar}, timeout=30)
if r.status_code != 200:
    sys.exit(f"Anahtar çalışmadı: {r.json().get('error', {}).get('message', r.text)}")
bilgi = r.json()

cfg_yol = KOK / "config.json"
cfg = json.loads(cfg_yol.read_text())
cfg["ig_access_token"] = anahtar
cfg["ig_user_id"] = bilgi["user_id"]
cfg_yol.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
cfg_yol.chmod(0o600)
subprocess.run(["xsel", "--clipboard", "--clear"])
print(f"Kaydedildi ✓  Hesap: @{bilgi['username']} ({bilgi.get('account_type')}), panodaki anahtar temizlendi.")
