FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Install Python dependencies
COPY src/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/

# Runtime entrypoint
ENTRYPOINT ["python", "-m", "src.main"]
