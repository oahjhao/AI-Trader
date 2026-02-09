# Base image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

# Set work directory inside container to match current layout
WORKDIR /home/ec2-user/AI-Trader

# Install system dependencies (build tools for scientific libs, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libffi-dev \
        git \
        procps \
        netcat-openbsd \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (leverages Docker layer cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Copy .env from EFS mount directory (if exists)
# Build argument for flexible .env path
ARG ENV_FILE_PATH=/mnt/efs/ai-trader/.env
RUN if [ -f "$ENV_FILE_PATH" ]; then \
      echo "📁 Copying .env from $ENV_FILE_PATH"; \
      cp "$ENV_FILE_PATH" /.env; \
    elif [ -f ".env" ]; then \
      echo "📁 Using local .env file"; \
      cp .env /.env; \
    else \
      echo "⚠️ No .env file found, container will use environment variables"; \
    fi

# Optional: pre-download NLTK data used by Jina search summarizer
# (if this step fails due to network limits, you can comment it out and
#  run scripts/install_nltk_resources.py at container startup instead.)
RUN if [ -f scripts/install_nltk_resources.py ]; then \
      python scripts/install_nltk_resources.py || true; \
    fi

# Note: docs/data symlink removed - frontend container uses direct volume mount
# The frontend expects data at /usr/share/nginx/html/data via EFS mount

# Expose default port for Web UI (scripts/start_ui.sh uses 8888)
EXPOSE 8888

# Default command: start an interactive shell.
# For production runs you typically override this, for example:
#   docker run --rm IMAGE python -m trader.runner configs/astock_config_hourly.json --signature YOUR_SIGNATURE
#   docker run --rm -p 8888:8888 IMAGE bash scripts/start_ui.sh
CMD ["bash"]
