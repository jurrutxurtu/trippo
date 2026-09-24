# Guía de Despliegue en Oracle Cloud Always Free (ARM64)

Esta guía explica paso a paso cómo crear y configurar una máquina virtual gratuita en **Oracle Cloud Infrastructure (OCI) Always Free**, configurar el dominio gratuito con **DuckDNS**, y preparar el entorno para el despliegue automático mediante **GitHub Actions**.

---

## 1. Crear la Instancia en Oracle Cloud

1. Entra a la consola de Oracle Cloud: [cloud.oracle.com](https://cloud.oracle.com).
2. Ve a **Compute** > **Instances** > **Create instance**.
3. Configuración recomendada:
   * **Name:** `trippo-server` (o el nombre que prefieras).
   * **Placement:** Mantén el default del Availability Domain.
   * **Image:** Haz clic en *Change image* y selecciona **Canonical Ubuntu** > **Ubuntu 24.04 Minimal (aarch64)**.
   * **Shape:** Haz clic en *Change shape*:
     * Shape series: **Ampere** (ARM-based processor).
     * Shape: **VM.Standard.A1.Flex** (Always Free Eligible).
     * OCPUs: **4** (o las que desees asignar, hasta 4 son gratis).
     * Memory: **24 GB** (gratis).
   * **Networking:**
     * Selecciona tu VCN existente o crea una nueva VCN con subred pública (*Create new virtual cloud network*).
     * Asigna una dirección IPv4 pública: **Assign a public IPv4 address**.
   * **Add SSH keys:**
     * Selecciona *Generate a key pair for me* (y descarga la clave privada `.key`) o pega tu clave pública existente (`id_ed25519.pub` o `id_rsa.pub`).
   * **Boot volume:** Puedes dejar el tamaño por defecto (50 GB) o aumentarlo hasta 100–200 GB dentro del límite gratuito.
4. Haz clic en **Create**. En unos minutos el estado pasará a **Running** y verás la **Public IP**.

---

## 2. Configurar el Cortafuegos de OCI (Security List)

Por defecto, OCI solo permite el puerto 22 (SSH). Para que la web funcione con HTTPS (Caddy / Let's Encrypt), debemos abrir los puertos 80 y 443 en la red cloud.

1. En la consola de OCI, ve a **Networking** > **Virtual Cloud Networks**.
2. Haz clic en tu VCN y luego en tu **Subnet** pública.
3. Haz clic en la **Default Security List for...**.
4. Haz clic en **Add Ingress Rules**:
   * **Source CIDR:** `0.0.0.0/0`
   * **IP Protocol:** `TCP`
   * **Destination Port Range:** `80,443`
   * **Description:** `HTTP and HTTPS for Caddy / Web`
5. Guarda la regla haciendo clic en **Add Ingress Rules**.

---

## 3. Configurar el Dominio Gratuito en DuckDNS

1. Ve a [duckdns.org](https://www.duckdns.org) e inicia sesión con GitHub o Google.
2. En la sección **domains**, introduce un subdominio para tu app (ej. `mitrippo`) y haz clic en **add domain**.
3. Verás tu dominio: `mitrippo.duckdns.org`.
4. En el campo **current ip**, introduce la **Public IP** de tu máquina de Oracle Cloud y pulsa **update ip**.
5. Copia tu **token** (una cadena alfanumérica que aparece en la cabecera).

---

## 4. Conectar a la VM y Ejecutar el Bootstrap

Conéctate por SSH a la máquina usando el usuario `ubuntu` y tu clave privada:

```bash
ssh -i /ruta/a/tu/clave.key ubuntu@<IP_PUBLICA_OCI>
```

Una vez dentro, ejecuta los siguientes comandos para inicializar el sistema con Docker, abrir el cortafuegos interno de Ubuntu y preparar `/opt/trippo`:

```bash
# Descargar y ejecutar el script de inicialización
curl -fsSL https://raw.githubusercontent.com/jurrutxurtu/trippo/master/scripts/oci_bootstrap.sh -o oci_bootstrap.sh
chmod +x oci_bootstrap.sh
./oci_bootstrap.sh
```

> **Nota:** El script abre los puertos 80 y 443 en el `iptables` de Ubuntu (que viene bloqueado de fábrica en las imágenes de OCI) e instala Docker oficial y Docker Compose.

### Configurar la actualización automática de DuckDNS (Opcional pero recomendado)

Para que tu dominio DuckDNS siempre apunte a tu IP aunque cambie:

```bash
# Crear el script de actualización en /opt/trippo
cat << 'EOF' | sudo tee /opt/trippo/duckdns_update.sh
#!/bin/bash
DOMAIN="TU_SUBDOMINIO"  # Sin .duckdns.org
TOKEN="TU_TOKEN_DUCKDNS"
curl -s "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=" > /dev/null
EOF

sudo chmod +x /opt/trippo/duckdns_update.sh

# Añadir a crontab para ejecutar cada 10 minutos
(crontab -l 2>/dev/null; echo "*/10 * * * * /opt/trippo/duckdns_update.sh") | crontab -
```

---

## 5. Configurar Secretos en GitHub para CI/CD

Para que el workflow de GitHub Actions pueda conectarse y desplegar automáticamente cada cambio en `master`:

1. Ve a tu repositorio en GitHub: `https://github.com/jurrutxurtu/trippo`.
2. Ve a **Settings** > **Secrets and variables** > **Actions**.
3. Añade los siguientes **Repository secrets**:

| Nombre del Secreto | Valor |
|---|---|
| `OCI_HOST` | La IP pública de tu máquina virtual o tu dominio (`mitrippo.duckdns.org`). |
| `OCI_USERNAME` | `ubuntu` |
| `OCI_SSH_KEY` | El contenido completo de tu clave privada SSH (`.key` o `id_rsa` / `id_ed25519`). Incluyendo `-----BEGIN OPENSSH PRIVATE KEY-----` y `-----END OPENSSH PRIVATE KEY-----`. |
| `DOMAIN` | Tu subdominio completo (ej. `mitrippo.duckdns.org`). |
| `MAPTILER_KEY` | *(Opcional)* Tu API key de MapTiler. |
| `GEMINI_API_KEY` | *(Opcional)* Tu API key de Gemini para sugerencias AI. |

---

## 6. Primer Despliegue Manual o Automático

Una vez configurados los secretos en GitHub, cualquier push a la rama `master` disparará el despliegue automático.

También puedes dispararlo manualmente en GitHub desde **Actions** > **CI/CD Pipeline** > **Run workflow**.

Cuando termine el pipeline, accede desde tu navegador a:
👉 `https://mitrippo.duckdns.org`

Caddy habrá obtenido automáticamente un certificado SSL gratuito de Let's Encrypt y la aplicación estará lista para usarse.

---

## 7. Arquitectura de Ingesta Web: Preprocesamiento en Cliente

Para permitir crear viajes directamente desde la interfaz web sin subir gigabytes de fotos originales a la nube ni agotar el disco de Oracle Cloud Free Tier:

1. **En el Navegador (Local):**
   - El usuario selecciona su carpeta de fotos mediante el selector de carpetas estándar del navegador.
   - Mediante JavaScript (`exifr` + Canvas API), el navegador extrae en local los metadatos EXIF (fecha/hora, coordenadas GPS, dimensiones) y genera miniaturas WebP optimizadas (256px y 1600px).
   - Un paquete ligero de ~30–50 MB (frente a 10 GB de fotos crudas) se envía por HTTP al servidor.
2. **En el Servidor (Oracle Cloud):**
   - El endpoint `POST /api/capsules/build-preprocessed` recibe el paquete y lanza la ingesta en segundo plano.
   - Ejecuta el pipeline de Trippo: normalización temporal, clustering de paradas, detección de pernoctas, geocodificación con OSM/Nominatim y sugerencias de IA.
   - Almacena la cápsula directamente en `/data/capsules/` y emite el progreso en tiempo real vía Server-Sent Events (SSE).
