FROM python:3.12.3

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend_requirements.txt
COPY model/requirements.txt ./model_requirements.txt

RUN pip install --no-cache-dir -r backend_requirements.txt
RUN pip install --no-cache-dir -r model_requirements.txt

# Copy the entire backend and model source code
COPY backend/ ./backend/
COPY model/ ./model/

# Set the python path so it can find the modules
ENV PYTHONPATH=/app

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]