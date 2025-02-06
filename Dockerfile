# Используем официальный базовый образ Python
FROM python:3.9-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копируем всё содержимое проекта в контейнер
COPY . .

# Открываем порт, который будет использовать Render (значение PORT задаётся переменной окружения)
EXPOSE 5055

# Команда для запуска приложения с использованием gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:$PORT"]