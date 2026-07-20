FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    unzip \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install CloakBrowser dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r tokenade && useradd -r -g tokenade -m tokenade

# Set working directory
WORKDIR /home/tokenade

# Copy requirements and install
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Copy application code
COPY . .

# Install tokenade
RUN pip install --no-cache-dir -e .

# Create necessary directories
RUN mkdir -p /home/tokenade/.tokenade/plugins \
    && mkdir -p /home/tokenade/.tokenade/sessions \
    && mkdir -p /home/tokenade/.tokenade/logs \
    && chown -R tokenade:tokenade /home/tokenade/.tokenade

# Switch to non-root user
USER tokenade

# Set environment variables
ENV TOKENADE_HOME=/home/tokenade/.tokenade
ENV PYTHONUNBUFFERED=1

# Default command
ENTRYPOINT ["tokenade"]
CMD ["--help"]
