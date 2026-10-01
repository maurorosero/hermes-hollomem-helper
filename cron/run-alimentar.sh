#!/usr/bin/env bash
# Wrapper para el cron: el scheduler recibe UNA ruta de script, sin flags.
# Este es el entry point del cron no_agent; el motor es alimentar.py.
#
# --escribir es lo que lo hace util: sin ese flag el script corre en dry-run y
# no toca la base. El cron SIEMPRE escribe.
#
# El stdout de aca es lo que Mauro recibe en Telegram. alimentar.py ya se cuida
# de imprimir solo el resumen de una linea (y nada si no hubo nada que hacer).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/env python3 "$DIR/alimentar.py" --escribir
