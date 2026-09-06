FROM python:3.12-slim

WORKDIR /app

# ffmpeg is used to generate playable placeholder clips for the seeded catalogue
# on first boot (see app/services/placeholder_video.py).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
