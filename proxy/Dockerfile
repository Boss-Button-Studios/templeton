FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# shared/ is mounted at /shared at runtime via docker-compose volume
ENV PYTHONPATH=/shared:/app

EXPOSE 8080 8081
CMD ["mitmdump", "--listen-port", "8080", "-s", "addon.py"]
