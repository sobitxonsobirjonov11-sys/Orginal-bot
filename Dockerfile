FROM python:3.10-slim

# Tizim dasturlari (FFmpeg va Node.js) ni o'rnatish
RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    && rm -rf /var/lib/apt-get/lists/*

WORKDIR /app

# Python kutubxonalarini o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Manba kodlarini nusxalash
COPY . .

# Botni ishga tushirish
CMD ["python", "main.py"]
