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
