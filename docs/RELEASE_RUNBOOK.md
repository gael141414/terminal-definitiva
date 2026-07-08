# Release runbook — ValueQuant Terminal

Este runbook define el proceso mínimo para cerrar un sprint, abrir PR, validar CI y fusionar cambios.

## 1. Preparar rama

Desde `main` actualizado:

```bash
git checkout main
git fetch origin
git reset --hard origin/main
git checkout -b nombre-del-sprint
git status --short
```

`git status --short` debe salir vacío antes de modificar archivos.

## 2. Validación local mínima

Antes de commitear:

```bash
python -m py_compile modulos/*.py scripts/*.py
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
python scripts/run_release_readiness.py
```

Si el sprint añade un contrato nuevo, ejecutarlo también directamente:

```bash
python scripts/test_nombre_del_contrato.py
```

## 3. Limpieza antes de commit

Eliminar backups temporales del sprint:

```bash
rm -f *.bak
rm -f modulos/*.bak_sprint_*
rm -f scripts/*.bak_sprint_*
```

Revisar estado:

```bash
git status --short
```

## 4. Commit

Añadir solo archivos concretos:

```bash
git add ruta/archivo1.py ruta/archivo2.py docs/archivo.md
git commit -m "feat: descripción breve"
```

No usar:

```bash
git add .
```

## 5. Push

```bash
git push -u origin nombre-del-sprint
```

## 6. Pull Request

Abrir PR contra `main`, inicialmente en draft si se quiere esperar al CI.

Checklist del PR:

```text
- Base: main
- Head: rama del sprint
- CI: success
- PR: mergeable
- Draft: false antes de fusionar
```

## 7. Merge

Fusionar solo si:

```text
CI success
Smoke tests locales OK
Release readiness READY
PR mergeable
Sin cambios inesperados
```

## 8. Actualizar local tras merge

```bash
git checkout main
git fetch origin
git reset --hard origin/main
git branch --delete nombre-del-sprint
git status --short
git log --oneline --decorate -5
```

## 9. QA final tras merge

```bash
python scripts/run_healthcheck.py
python scripts/run_smoke_tests.py --strict
python scripts/run_release_readiness.py
streamlit run app.py
```

## 10. Criterios de bloqueo

No fusionar si ocurre cualquiera de estos casos:

- `run_smoke_tests.py --strict` falla.
- `run_release_readiness.py` devuelve `BLOCKED`.
- Hay errores de compilación.
- El PR no es mergeable.
- Hay archivos de backup o secretos en `git status`.
- Se han tocado módulos financieros sin contrato o validación asociada.
