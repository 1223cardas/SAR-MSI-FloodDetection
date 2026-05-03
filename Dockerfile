FROM sentineldatahub/esa-snap:latest

WORKDIR /app

# Install Python dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY requirements.txt .
COPY pyproject.toml .
COPY README.md .
COPY INSTALL.md .
COPY .env.example .env
COPY main.py .
COPY processors.py .
COPY S1/ S1/
COPY S2/ S2/
COPY tests/ tests/

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Install in development mode
RUN pip install -e .

# Create data directories
RUN mkdir -p S1/data/products S1/data/region_of_interest S1/workflows S1/out
RUN mkdir -p Imagens ndwi_work

# Set up environment for SNAP (already in the base image)
ENV SNAP_DIRECTORY=/opt/snap

# Default command: show help
CMD ["sar-msi", "--help"]
