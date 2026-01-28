FROM python:3.11-slim

# Устанавливаем шрифты для PDF с кириллицей
RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаём директорию для БД
RUN mkdir -p /data

# Переменная для БД вне контейнера
ENV DB_PATH=/data/pet_health.db

CMD ["python", "bot.py"]
