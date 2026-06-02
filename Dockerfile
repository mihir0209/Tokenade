# Tokenade - Production-grade token shifting tool
# Multi-stage build for minimal image size

# Stage 1: Build dependencies
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime image
FROM python:3.11-slim

LABEL maintainer="Tokenade Team"
LABEL description="Production-grade token shifting and session portability tool"

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright dependencies
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    # Secret storage for Linux
    libsecret-1-0 \
    secret-tool \
    # General utilities
    curl \
    jq \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY tokenade/ ./tokenade/
COPY setup.py .
COPY README.md .
COPY requirements.txt .

# Install tokenade package
RUN pip install --no-cache-dir -e .

# Install Playwright browsers
RUN playwright install chromium && playwright install-deps chromium

# Create data directories
RUN mkdir -p /app/sessions /app/browser_data /app/.fingerprints /app/reports

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV TOKENADE_DATA_DIR=/app
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import tokenade; print(tokenade.__version__)" || exit 1

# Default command
ENTRYPOINT ["tokenade"]
CMD ["--help"]
