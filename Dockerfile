# Usamos una imagen de Python ligera
FROM python:3.11-slim

# Evita que Python genere archivos .pyc y permite ver logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Instalamos dependencias del sistema necesarias (si las hubiera)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiamos solo el archivo de requerimientos primero
# Nota: Asegúrate de tener un archivo requirements.txt
COPY requirements.txt .

# Instalamos las librerías de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código del proyecto
COPY . .

# Exponemos el puerto que usa uvicorn en tu archivo main_cache.py
EXPOSE 3000

# Comando para ejecutar la aplicación
CMD ["python", "main_cache.py"]