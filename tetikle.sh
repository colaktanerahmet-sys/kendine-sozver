#!/bin/bash
# Yedek zamanlayıcı (bilgisayardaki cron): GitHub'ın kendi zamanlayıcısı saatlerce gecikebiliyor.
# Çalışan/bekleyen bir paylaşım işi yoksa 'oto' işini başlatır; ne paylaşılacağına iş kendisi karar verir.
export PATH=/home/taner/.local/bin:/usr/local/bin:/usr/bin:/bin
R=colaktanerahmet-sys/kendine-sozver
aktif=$(gh run list -R $R -w paylas.yml -L 5 --json status -q '[.[]|select(.status!="completed")]|length' 2>/dev/null) || exit 0
[ "$aktif" = "0" ] && gh workflow run paylas.yml -R $R -f vakit=oto && echo "$(date '+%F %T') tetiklendi"
