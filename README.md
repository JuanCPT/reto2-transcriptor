# YT Transcriptor — Matrix Edition

## Descripción

YT Transcriptor — Matrix Edition es una aplicación web que permite transcribir archivos de audio y video a texto mediante Python y faster-whisper. Su interfaz utiliza un diseño visual inspirado en Matrix.

Este proyecto se desarrolló como parte del Reto 2, **Prepara y lanza tu aplicación web**, del módulo Despliegue de aplicaciones web y móviles v2 de la Universidad Virtual del Estado de Guanajuato (UVEG).

## Funcionalidades

- Selección y carga de archivos de audio y video.
- Configuración del modelo de transcripción y del idioma.
- Procesamiento mediante faster-whisper.
- Visualización del texto transcrito con marcas de tiempo.
- Copia del texto y descarga del resultado en formato TXT.
- Ejecución local mediante un backend desarrollado con Flask.

El backend permite utilizar CPU y contempla la aceleración por GPU cuando el hardware y las dependencias compatibles están disponibles.

## Tecnologías utilizadas

- Python 3.13
- Flask
- faster-whisper
- PyAV
- HTML5
- CSS3
- JavaScript
- Apache HTTP Server mediante XAMPP
- GitHub para el versionamiento del proyecto

## Estructura del proyecto

text
reto2-transcriptor/
├── backend/
│   ├── app.py
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── css/
    │   └── style.css
    └── js/
        └── app.js


## Preparación del entorno

1. Instalar Python 3.13.
2. Crear un entorno virtual dentro de la carpeta `backend`.
3. Instalar las dependencias declaradas en `requirements.txt`.
4. Ejecutar el backend Flask.
5. Copiar los archivos de `frontend` al directorio de publicación de Apache.
6. Abrir la aplicación desde el navegador.

## Ejecución local

Desde PowerShell, entrar en la carpeta `backend` y ejecutar:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Con Apache iniciado en XAMPP y los archivos web publicados en `C:\xampp\htdocs\transcriptor`, abrir:

http://localhost/transcriptor/

El backend local está disponible en:

http://127.0.0.1:5000

## Pruebas realizadas

Se comprobó el acceso a la interfaz mediante Apache, la comunicación con el backend Flask, el procesamiento de un archivo de video y la generación de una transcripción descargable en formato TXT.

## Consideraciones

La velocidad depende de la duración del archivo, el modelo seleccionado y los recursos disponibles en el equipo. El uso de GPU requiere hardware compatible y las dependencias necesarias. Esta configuración corresponde a un entorno de desarrollo local y no representa por sí sola un despliegue público en Internet.
