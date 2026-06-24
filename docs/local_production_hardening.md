# Hardening local de ValueQuant Terminal

Este documento define una base mínima para ejecutar ValueQuant Terminal en local sin subir secretos, datos generados ni logs al repositorio.

## 1. Archivos que no deben subirse

No deben aparecer en `git status` como archivos a commitear:

```text
.env
.streamlit/secrets.toml
data/
exports/
logs/
scripts/*.local.sh
*.bak
```

Estos patrones están cubiertos por `.gitignore`.

## 2. Healthcheck local

Ejecuta:

```bash
python scripts/run_healthcheck.py
```

Para crear directorios runtime si no existen:

```bash
python scripts/run_healthcheck.py --fix
```

El healthcheck valida:

```text
- Versión de Python
- Archivos críticos del proyecto
- Directorios runtime
- Dependencias principales instaladas
- Patrones críticos en .gitignore
- FMP_API_KEY configurada
- Configuración opcional de Telegram
- Existencia local de .env y secrets.toml
```

## 3. Configuración mínima recomendada

En `.env` o `.streamlit/secrets.toml`:

```env
FMP_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
VALUEQUANT_DEBUG=false
```

Telegram es opcional. FMP es obligatoria para análisis financieros completos.

## 4. Validación antes de usar automatizaciones

Antes de usar `scripts/run_opportunity_briefing.py` o cualquier plantilla cron:

```bash
python scripts/run_healthcheck.py --fix
python scripts/run_opportunity_briefing.py
```

Después revisa:

```bash
ls -la exports/briefings
ls -la data/automation_log.jsonl
```

## 5. Reglas de seguridad

- No hardcodear claves en `.py`.
- No commitear `.env` ni `secrets.toml`.
- No commitear `data/`, `exports/` ni `logs/`.
- No activar cron hasta validar varios días manualmente.
- Telegram debe seguir con confirmación/manual o flags explícitos.
- Si una clave se pega en un chat, issue o commit, hay que revocarla y regenerarla.

## 6. Comando de diagnóstico rápido

```bash
git status --short
python scripts/run_healthcheck.py
python -m py_compile app.py modulos/config.py modulos/scoring_engine.py modulos/research_core.py
```

Resultado esperado:

```text
- `git status` sin secretos ni datos generados.
- Healthcheck sin errores.
- Compilación sin salida.
```
