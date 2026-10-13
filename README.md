# YT Transcriptor — Matrix Edition

Aplicación web para transcribir archivos de audio y video a texto mediante Python y `faster-whisper`, con una interfaz visual inspirada en Matrix.

Este proyecto se desarrolla como parte del **Reto 2: Prepara y lanza tu aplicación web**, del módulo **Despliegue de aplicaciones web y móviles v2**, de la Universidad Virtual del Estado de Guanajuato (UVEG).

## 1. Descripción del proyecto

YT Transcriptor — Matrix Edition permite al usuario seleccionar un archivo de audio o video, procesarlo mediante un servicio backend en Python y obtener su contenido transcrito en texto.

La aplicación utiliza una arquitectura dividida en dos componentes principales:

- **Frontend:** interfaz desarrollada con HTML, CSS y JavaScript, servida localmente mediante Apache de XAMPP.
- **Backend:** API desarrollada con Python y Flask, encargada de gestionar las solicitudes de transcripción mediante `faster-whisper`.

La comunicación entre ambos componentes se realiza mediante solicitudes HTTP a una API local.

## 2. Funcionalidades principales

- Selección y envío de archivos de audio y video compatibles con las bibliotecas instaladas.
- Transcripción automática mediante `faster-whisper`.
- Procesamiento de las solicitudes en segundo plano.
- Consulta del estado de las tareas de transcripción.
- Visualización del progreso y resultado del procesamiento en la interfaz.
- Descarga del texto transcrito en un archivo `.txt`.
- Diseño visual inspirado en Matrix.
- Comprobación del estado del servicio backend mediante un endpoint de salud.
- Ejecución local con posibilidad de utilizar CPU y, cuando el entorno lo permite, GPU compatible.

## 3. Tecnologías utilizadas

| Tecnología | Función |
|---|---|
| HTML5 | Estructura de la interfaz web |
| CSS3 | Diseño y presentación visual |
| JavaScript | Interacción con el usuario y comunicación con la API |
| Python | Lógica del backend |
| Flask | Creación de la API web |
| Flask-CORS | Configuración de solicitudes entre orígenes permitidos |
| faster-whisper | Motor de transcripción de audio |
| PyAV | Procesamiento multimedia |
| Apache de XAMPP | Servidor local del frontend |

## 4. Estructura del proyecto

```text
reto2-transcriptor/
├── README.md
├── backend/
│   ├── app.py
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── css/
    │   ├── style.css
    │   └── style.min.css
    └── js/
        ├── app.js
        └── app.min.js
```

Los archivos `style.css` y `app.js` corresponden a las versiones de desarrollo. Los archivos `style.min.css` y `app.min.js` contienen versiones minificadas utilizadas por la interfaz para reducir el tamaño de los recursos cargados.

## 5. Requisitos previos

Para ejecutar el proyecto localmente se necesita:

- Windows.
- Python instalado y disponible desde la terminal.
- XAMPP con el servicio Apache.
- Conexión a internet para instalar las dependencias.
- Espacio disponible para las dependencias y los modelos de transcripción.

La aceleración por GPU depende de la compatibilidad del hardware, los controladores y las bibliotecas necesarias. Si no se encuentra disponible, el procesamiento puede realizarse mediante CPU.

## 6. Preparación del backend

### 6.1. Abrir la terminal

Abre PowerShell y cambia al directorio `backend` del proyecto. Sustituye la ruta del ejemplo por la ubicación donde hayas guardado el repositorio.

```powershell
cd "RUTA\DEL\PROYECTO\backend"
```

### 6.2. Crear un entorno virtual

```powershell
py -m venv .venv
```

### 6.3. Instalar las dependencias

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Las bibliotecas necesarias se encuentran declaradas en `requirements.txt`.

### 6.4. Iniciar el backend

Desde el directorio `backend`, ejecuta:

```powershell
.\.venv\Scripts\python.exe app.py
```

El servicio estará disponible localmente en:

`http://127.0.0.1:5000`

Mantén abierta la terminal mientras utilices la aplicación, ya que ahí se ejecuta el backend.

## 7. Preparación del frontend con XAMPP

1. Inicia Apache desde el panel de control de XAMPP.
2. Copia el contenido de la carpeta `frontend` del repositorio dentro de:

   `C:\xampp\htdocs\transcriptor`

3. Comprueba que el archivo `index.html` se encuentre directamente en esa carpeta:

```text
C:\xampp\htdocs\transcriptor\
├── index.html
├── css\
└── js\
```

4. Abre el navegador y accede a:

   `http://localhost/transcriptor/`

5. Verifica que el backend siga ejecutándose en la terminal.

**Importante:** Apache sirve la interfaz web y Flask ejecuta el procesamiento de las transcripciones. Ambos servicios deben estar activos para utilizar la aplicación completa.

## 8. Endpoints de la API

El backend expone los siguientes endpoints locales:

| Método | Endpoint | Función |
|---|---|---|
| GET | `/api/health` | Consultar el estado del servicio |
| POST | `/api/transcribe` | Enviar una solicitud de transcripción |
| GET | `/api/jobs/<job_id>` | Consultar el estado de una tarea de transcripción |

La interfaz JavaScript utiliza estos endpoints para comunicarse con el backend, iniciar el procesamiento y consultar sus resultados.

Para comprobar el estado básico del servicio, abre:

`http://127.0.0.1:5000/api/health`

## 9. Flujo de funcionamiento

1. El usuario abre la interfaz desde el navegador.
2. Selecciona un archivo de audio o video compatible.
3. El frontend envía la solicitud al backend.
4. Flask gestiona la tarea de transcripción.
5. La interfaz consulta el estado del procesamiento.
6. Al finalizar, el usuario puede consultar y descargar el texto resultante.

## 10. Consideraciones de ejecución

- El frontend depende de que Apache esté activo.
- La transcripción depende de que el backend esté ejecutándose.
- El tiempo de procesamiento depende de la duración del archivo, el modelo empleado y los recursos del equipo.
- El rendimiento puede variar entre CPU y GPU.
- La aplicación está preparada para ejecución local; este repositorio no incluye, por sí mismo, la configuración necesaria para publicar el sistema completo en internet.
- La dirección `127.0.0.1` corresponde al equipo local. Para un despliegue público sería necesario configurar la infraestructura, la seguridad, el acceso a la API y los servicios correspondientes.

## 11. Solución de problemas

**La página no abre**

Comprueba que Apache esté activo y que `index.html` se encuentre en `C:\xampp\htdocs\transcriptor`.

**La interfaz no se comunica con el backend**

Verifica que Flask esté ejecutándose y que el servicio esté disponible en `http://127.0.0.1:5000`.

**Se producen errores al instalar dependencias**

Comprueba la versión de Python, que el entorno virtual esté activado o que se utilice el ejecutable correcto, y revisa el mensaje de error de la instalación.

**La transcripción tarda en finalizar**

El procesamiento puede tardar según el tamaño del archivo y la capacidad del equipo. Comprueba el estado de la tarea y los mensajes mostrados en la terminal del backend.

## 12. Autoría y propósito académico

Proyecto desarrollado con fines académicos para aplicar conceptos de preparación, configuración y ejecución de una aplicación web con frontend y backend.

**Curso:** Despliegue de aplicaciones web y móviles v2  
**Institución:** Universidad Virtual del Estado de Guanajuato (UVEG)  
**Actividad:** Reto 2 — Prepara y lanza tu aplicación web

