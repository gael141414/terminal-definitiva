# ValueQuant Terminal — Scheduler seguro

Este documento prepara la automatización local del briefing sin activarla automáticamente.

## Objetivo

Ejecutar el runner local:

```bash
python scripts/run_opportunity_briefing.py
```

y, cuando esté validado, permitir envío a Telegram con confirmación explícita desde script:

```bash
python scripts/run_opportunity_briefing.py --send-telegram --yes
```

## Estado actual

La automatización real no está activada por defecto. El sistema ya dispone de:

- `modulos/briefing_runner.py`: motor de ejecución local.
- `scripts/run_opportunity_briefing.py`: entrada por terminal.
- `data/automation_settings.json`: configuración local de frecuencia.
- `data/automation_log.jsonl`: log de generación y envíos.
- `modulos/automation_schedule.py`: control anti-duplicados.
- `modulos/manual_delivery.py`: envío manual a Telegram con confirmación.

## Requisitos previos

Desde la raíz del proyecto:

```bash
source .venv/bin/activate
python -m py_compile modulos/briefing_runner.py scripts/run_opportunity_briefing.py
python scripts/run_opportunity_briefing.py
```

Debe generar archivos en:

```text
exports/briefings/
```

Antes de enviar a Telegram, comprueba:

```bash
python - <<'PY'
from modulos.config import CONFIG
print('Telegram token configurado:', bool(CONFIG.telegram_bot_token))
print('Telegram chat configurado:', bool(CONFIG.telegram_chat_id))
PY
```

## Ejecución manual recomendada

Generar briefing sin enviar:

```bash
python scripts/run_opportunity_briefing.py --format all
```

Generar solo mensaje compacto:

```bash
python scripts/run_opportunity_briefing.py --format compact
```

Enviar a Telegram, solo si la configuración ya está validada:

```bash
python scripts/run_opportunity_briefing.py --format compact --send-telegram --yes
```

Forzar frecuencia solo en ejecución manual excepcional:

```bash
python scripts/run_opportunity_briefing.py --format compact --send-telegram --yes --force-frequency
```

## Plantillas de shell

Hay plantillas preparadas en:

```text
scripts/valuequant_briefing_daily.example.sh
scripts/valuequant_briefing_weekly.example.sh
```

Copia una plantilla fuera del repo o a un archivo local ignorado por Git:

```bash
cp scripts/valuequant_briefing_daily.example.sh scripts/valuequant_briefing_daily.local.sh
chmod +x scripts/valuequant_briefing_daily.local.sh
```

Edita estas variables:

```bash
PROJECT_DIR="/ruta/absoluta/a/terminal-limpia"
VENV_DIR="$PROJECT_DIR/.venv"
```

Prueba manual:

```bash
scripts/valuequant_briefing_daily.local.sh
```

## Cron: preparación, no activación automática

Para editar cron manualmente:

```bash
crontab -e
```

Ejemplo diario a las 08:30:

```cron
30 8 * * 1-5 /home/gael/Escritorio/terminal-limpia/scripts/valuequant_briefing_daily.local.sh >> /home/gael/Escritorio/terminal-limpia/logs/cron_briefing.log 2>&1
```

Ejemplo semanal los domingos a las 19:00:

```cron
0 19 * * 0 /home/gael/Escritorio/terminal-limpia/scripts/valuequant_briefing_weekly.local.sh >> /home/gael/Escritorio/terminal-limpia/logs/cron_briefing.log 2>&1
```

No pegues estos ejemplos sin adaptar rutas absolutas.

## Verificación posterior

Después de una ejecución:

```bash
ls -lah exports/briefings | tail
cat data/automation_log.jsonl | tail -n 5
```

Desde la app:

```text
💼 Cartera y Decisión → ⚙️ Centro de Automatización → Historial
```

## Validación cruzada SEC↔FMP (nocturna)

Job independiente del briefing: recalcula los ratios de la watchlist a
partir de los 10-K reales en SEC EDGAR y los contrasta con FMP (Sub-fases
0-3 del bloque SEC↔FMP). También cron local, por el mismo motivo que el
briefing: necesita `data/watchlist.json` real, que no existe en un checkout
de CI.

Ejecución manual:

```bash
python scripts/run_sec_validation.py
```

Con aviso a Telegram si aparecen discrepancias nuevas desde la corrida
anterior (nunca se envía sin `--yes`):

```bash
python scripts/run_sec_validation.py --send-telegram --yes
```

Ajustar tope de tickers/noche, pausa entre tickers y años de histórico:

```bash
python scripts/run_sec_validation.py --max-tickers 20 --pause-seconds 2 --years 5
```

Dispone de:

- `modulos/sec_validation_runner.py`: motor de ejecución local (selección de
  tickers, comparación, persistencia inmediata por ticker, notificación).
- `modulos/sec_validation_store.py`: persistencia (`data/sec_validation_history.json`
  + campo compacto `last_sec_validation` en `data/watchlist.json`).
- `scripts/run_sec_validation.py`: entrada por terminal.
- `scripts/valuequant_sec_validation.example.sh`: plantilla de cron.

Plantilla de cron (copiar fuera del patrón `*.local.sh`, igual que el
briefing):

```bash
cp scripts/valuequant_sec_validation.example.sh scripts/valuequant_sec_validation.local.sh
chmod +x scripts/valuequant_sec_validation.local.sh
```

```cron
0 2 * * * /home/gael/Escritorio/terminal-limpia/scripts/valuequant_sec_validation.local.sh >> /home/gael/Escritorio/terminal-limpia/logs/cron_sec_validation.log 2>&1
```

Selección de tickers: rotación "el más antiguo sin verificar primero" — un
ticker nunca comprobado siempre entra antes que uno ya comprobado, así que
con un tope de 40/noche una watchlist más grande se cubre en varias noches
sin intervención manual.

Verificación posterior:

```bash
cat data/sec_validation_history.json | python -m json.tool | head -40
```

Desde la app:

```text
💼 Cartera y Decisión → ⚙️ Centro de Automatización → Historial
(evento event_type = sec_validation_run)
```

## Reglas de seguridad

- No subas `.env` ni `.streamlit/secrets.toml`.
- No guardes tokens en scripts versionados.
- No uses `--force-frequency` en cron.
- Mantén `--send-telegram --yes` solo cuando el briefing haya sido validado varios días.
- Revisa `data/automation_log.jsonl` si un envío falla.

## Roadmap posterior

Antes de activar automatización real en producción:

1. Validar varios briefings diarios sin envío.
2. Activar envío manual desde UI.
3. Probar runner local con `--send-telegram --yes`.
4. Activar cron solo si los logs son consistentes.
5. Añadir notificación de error si falla el runner.
