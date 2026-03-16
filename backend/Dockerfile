FROM python:3.11-slim

WORKDIR /app

# Copy and install dependencies first (cache layer)
COPY requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy the backend package
COPY . /app/backend/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:socket_app", "--host", "0.0.0.0", "--port", "8000"]
