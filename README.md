# Sistema de Nómina Semanal — Mega Fresh Produce
## Guía de Instalación y Despliegue

---

## Estructura del proyecto

```
nomina_app/
├── app.py          — Aplicación Flask, todas las rutas API
├── models.py       — Modelos de base de datos (SQLAlchemy)
├── calculos.py     — Motor de cálculo de nómina (ISR, IMSS, etc.)
├── exportar.py     — Generador de Excel formato NOMINA TOPES
├── templates/
│   └── index.html  — Interfaz web (SPA)
├── requirements.txt
└── nomina.db       — Base de datos SQLite (se crea automáticamente)
```

---

## Instalación local (desarrollo)

```bash
cd nomina_app
cp .env.example .env
pip install -r requirements.txt
python app.py
# Abrir: http://localhost:5000
```

### Archivo `.env`

El proyecto lee automáticamente un archivo `.env` en la raíz del proyecto.
Primero copia el ejemplo:

```bash
cp .env.example .env
```

Luego edita `.env` con tus datos reales.

Si quieres usar tu servidor MySQL, estas son las variables importantes:

```bash
DB_DIALECT=mysql
DB_HOST=tu-host-o-ip
DB_PORT=3306
DB_NAME=nomina
DB_USER=usuario
DB_PASSWORD=tu_password
DB_DRIVER=pymysql
SECRET_KEY=una-clave-segura
```

También puedes seguir usando `DATABASE_URL` si prefieres una sola cadena de conexión; esa variable tiene prioridad.

---

## Despliegue en AWS

### Opción A: EC2 (recomendada para uso interno)

1. **Lanzar instancia EC2** (t3.small o t3.medium, Amazon Linux 2023 o Ubuntu 22.04)

2. **Instalar dependencias:**
```bash
sudo yum update -y  # o apt-get update
sudo yum install -y python3-pip nginx
pip3 install -r requirements.txt
```

3. **Subir archivos:**
```bash
scp -r nomina_app/ ec2-user@TU-IP:/home/ec2-user/
```

4. **Crear servicio systemd** (`/etc/systemd/system/nomina.service`):
```ini
[Unit]
Description=Sistema Nomina MFP
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/nomina_app
Environment="DATABASE_URL=sqlite:////home/ec2-user/nomina_app/nomina.db"
Environment="SECRET_KEY=TU-CLAVE-SECRETA-AQUI"
ExecStart=/usr/local/bin/gunicorn -w 4 -b 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable nomina
sudo systemctl start nomina
```

5. **Configurar Nginx** (`/etc/nginx/conf.d/nomina.conf`):
```nginx
server {
    listen 80;
    server_name TU-DOMINIO-O-IP;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 50M;
    }
}
```

```bash
sudo systemctl restart nginx
```

### Opción B: RDS PostgreSQL (para producción con múltiples usuarios)

Cambiar la variable de entorno:
```bash
DATABASE_URL=postgresql://usuario:password@tu-rds.amazonaws.com/nomina
```

Y actualizar `requirements.txt`:
```
psycopg2-binary>=2.9
```

---

## Estructura de la base de datos

### `sn_trabajadores`

Campos principales:
- `trabajador_id` (PK)
- `imss` (único)
- `rfc`, `curp`
- `nombre`, `apellido_pat`, `apellido_mat`
- `tipo_trabajador`, `area_funcional`, `puesto`, `periodo_pago`
- `salario_dia_real`, `sbc_dia`, `sdi_dia`, `factor_integracion`, `costo_hr_extra`
- `banco`, `num_cuenta`, `num_tarjeta`, `forma_pago`
- `credito_infonavit`, `factor_infonavit`
- `vac_del_periodo`, `vac_acumuladas`
- `fecha_ingreso_real`, `fecha_ingreso_imss`, `fecha_baja`
- `estatus`, `tipo_baja`, `observaciones`
- `created_at`, `updated_at`

### `sn_periodos_nomina`

Campos principales:
- `periodo_nomina_id` (PK)
- `num_semana`, `anio`
- `fecha_inicio`, `fecha_fin`, `fecha_pago`
- `estatus`
- `uma_vigente`, `sm_vigente`, `se_decreto`
- `created_at`, `created_by`

### `sn_incidencias`

Campos principales:
- `incidencia_id` (PK)
- `periodo_nomina_id` (FK a `sn_periodos_nomina.periodo_nomina_id`)
- `trabajador_id` (FK a `sn_trabajadores.trabajador_id`)
- `dias_trabajados`, `dias_incapacidad`
- `tiene_bono`, `horas_extras_reales`, `horas_extras_fiscales`
- `vacaciones_dias`, `prima_vac_dias`
- `despensa`, `asistencia`, `puntualidad`, `compensacion`, `observacion`
- `calculado`
- `sueldo_fiscal`, `bono_fiscal`, `hrs_extra_fiscal`, `vacaciones_fiscal`, `prima_vac_fiscal`
- `suma_fiscal`, `cuota_obrera`, `isr_calcula`, `sub_emp_acre`, `isr_neto`, `infonavit`
- `suma_deduc`, `neto_fiscal`
- `suma_real`, `neto_real`, `diferencia`
- `updated_at`, `updated_by`

### `sn_historial_movimientos`

Registra altas, bajas y reingresos.
- `historial_movimiento_id` (PK)
- `trabajador_id` (FK a `sn_trabajadores.trabajador_id`)
- `tipo_movimiento` (`ALTA`, `BAJA`, `REINGRESO`, `CAMBIO`)
- `fecha_movimiento`
- `riesgo_reingreso` (`NORMAL`, `MEDIO`, `ALTO`)
- `motivo`
- `creado_en`
- `creado_por`

### Relaciones
- Un `sn_trabajador` tiene muchas `sn_incidencias`
- Un `sn_periodo_nomina` tiene muchas `sn_incidencias`
- Cada `incidencia` pertenece a un `trabajador` y a un `periodo_nomina`
- Un `sn_trabajador` tiene muchos `sn_historial_movimientos`

### Reingreso
- Si un `NSS` ya existía y estaba en baja, la app devuelve una alerta con la fecha de baja y el riesgo.
- Para reactivarlo, envía `reactivar=true` al crear el alta con el mismo `NSS`.
- Los campos marcados con `*` en el formulario de alta son obligatorios.

---

## Flujo de trabajo semanal

### 1. Primera vez — Importar catálogo
- Ir a **Altas / Bajas** → pestaña **Importar desde Excel**
- Subir archivo `1_1_BDA_MEGA_FRESH_P_V2_O.xlsb`
- Sistema importa todos los trabajadores con estatus ALTA

### 2. Cada semana
1. **Períodos** → **+ Nuevo Período** → seleccionar fechas
   - Se crean incidencias vacías para todos los activos
2. **Captura** → editar días trabajados, bono, horas extras, vacaciones
   - Guardar con el botón 💾
3. **Prenómina** → **🧮 Calcular** → revisar tabla
4. **Exportar**:
   - **⬇️ Excel Permanentes** → enviar a Nomipaq
   - **⬇️ Excel Eventuales** → enviar a Nomipaq
   - La hoja **DIFERENCIAS** contiene los pagos en efectivo

---

## Parámetros fiscales 2026

| Concepto | Valor |
|---|---|
| UMA diaria | $117.31 |
| Salario Mínimo diario | $315.04 |
| SE Decreto mensual (Feb-Dic 2026) | $535.65 |
| SE Decreto límite mensual | $11,492.66 |
| Cuota obrera IMSS base | 2.375% del SBC |
| Cuota obrera IMSS excedente (>3×UMA/día) | +0.4% |

---

## Actualización anual (enero de cada año)

En `calculos.py`, actualizar:
- `UMA_DIA` — valor publicado por CONSAR
- `SM_DIA` — salario mínimo STPS
- `TABLA_ISR_MENSUAL` — tabla Art. 96 LISR (DOF)
- `TABLA_SUBSIDIO_MENSUAL` — tabla SAT
- Agregar fila a `DECRETO_SE` con el nuevo SE

---

## Notas técnicas importantes

### Separación fiscal / no fiscal
- **Fiscal (SBC):** se timbra en CFDI, se exporta a Nomipaq
- **Diferencia real:** pago en efectivo, aparece en hoja DIFERENCIAS
- **Horas extras reales:** valor fijo por puesto ($30/$35/$60), NO va al fiscal
- **Horas extras fiscales:** cálculo ISR (SD/8×2), máximo 9 horas dobles

### ISR — Método mensualizado
```
base_mensual = suma_percepciones_fiscales / 7 × 30.4
ISR_mensual  = tabla_SAT(base_mensual)
SE_mensual   = SE_decreto (fijo por decreto, verificado en archivo)
ISR_semanal  = (ISR_mensual - SE_mensual) / 30.4 × días_laborados
```

### IMSS Cuota Obrera (verificado contra archivos históricos)
```
cuota = SBC × 2.375% × días
      + max(0, SBC - 3×UMA) × 0.4% × días
```
