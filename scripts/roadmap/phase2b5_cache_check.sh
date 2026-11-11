#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1

echo "== lightkurve cache =="
LK_CACHE="$HOME/.lightkurve/cache"
if [ -d "$LK_CACHE" ]; then
    echo "  cache dir: $LK_CACHE"
    find "$LK_CACHE" -type f 2>/dev/null | wc -l | xargs echo "  total files:"
    du -sh "$LK_CACHE" 2>/dev/null
    echo
    echo "  sample files:"
    find "$LK_CACHE" -type f -name "*.fits" 2>/dev/null | head -5
else
    echo "  no lightkurve cache — re-download required"
fi

echo
echo "== astroquery cache =="
AQ_CACHE="$HOME/.astropy/cache"
[ -d "$AQ_CACHE" ] && du -sh "$AQ_CACHE" 2>/dev/null || echo "  no astroquery cache"

echo
echo "== disk usage overall =="
df -h "$HOME" | tail -1
