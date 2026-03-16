FROM python:3.11-slim

WORKDIR /app

# Copy and install dependencies first (Docker cache layer)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy the backend source into the correct package path
# The import path is "backend.*" so we need /app/backend/
COPY . /app/backend/

EXPOSE 8000

# PYTHONPATH=/app ensures "import backend.xxx" resolves
ENV PYTHONPATH=/app
CMD ["python", "-m", "uvicorn", "backend.main:socket_app", "--host", "0.0.0.0", "--port", "8000"]
