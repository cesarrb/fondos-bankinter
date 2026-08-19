# Fondos Bankinter — descarga automática

Descarga cada día el catálogo completo de fondos del buscador de Bankinter
(fuente de datos: Allfunds / Morningstar) y lo guarda en `data/fondos_latest.csv`,
con una copia con fecha en `data/history/`.

> Aviso: usa un endpoint interno no documentado de Bankinter, para uso personal.
> Podría cambiar o dejar de funcionar sin previo aviso.

## Contenido
- `extract_fondos.py` — el script de descarga (solo necesita `requests`).
- `requirements.txt` — dependencias.
- `.github/workflows/fondos.yml` — automatización en GitHub Actions (L-V a las 06:00 UTC).

---

## Opción A · GitHub Actions (recomendada, todo desde el navegador)

1. Entra en https://github.com y pulsa **+ → New repository**.
2. Nombre: `fondos-bankinter`. Marca **Private**. Pulsa **Create repository**.
3. En la página del repo vacío: **Add file → Upload files**.
4. **Arrastra TODO el contenido** de esta carpeta (incluida la carpeta oculta `.github`).
   GitHub respeta la estructura. Pulsa **Commit changes**.
5. Da permiso de escritura al robot:
   **Settings → Actions → General → Workflow permissions →** elige
   **"Read and write permissions" →** *Save*.
6. Prueba: pestaña **Actions → Descarga fondos Bankinter → Run workflow**.
   En 2-3 min aparecerá `data/fondos_latest.csv`. Ábrelo y pulsa **Download (raw)**.
7. A partir de ahí se ejecuta solo cada día laborable. Cada ejecución hace un
   *commit*, así que en **el historial del repo ves cómo cambian las métricas día a día**.
   Si algún día falla, GitHub te avisa por email.

## Opción B · Synology NAS (para tenerlo también en casa)

1. **Centro de paquetes** → instala **Python 3**.
2. Con **File Station**, crea la carpeta `fondos` y sube `extract_fondos.py`.
3. **Panel de control → Programador de tareas → Crear → Tarea programada → Script definido por el usuario**.
   - *General*: nombre, usuario = tu administrador.
   - *Programar*: diariamente, la hora que quieras.
   - *Configuración de tareas → Ejecutar comando*:
     ```
     cd /volume1/fondos && python3 -m pip install --user requests; python3 extract_fondos.py >> run.log 2>&1
     ```
   - Si `python3` no lo encuentra, prueba con la ruta completa `/usr/local/bin/python3`.
4. Guarda. Clic derecho en la tarea → **Ejecutar** para probar.
   El CSV queda en `/volume1/fondos/data/`, accesible desde toda tu red.
