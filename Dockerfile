FROM python:3.11-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# Default: API + UI in ONE container (Render / Hugging Face Spaces). docker-compose overrides this.
EXPOSE 7860 8000
CMD ["bash", "docker/start.sh"]
