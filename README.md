# SAR-MSI Flood Detection

Projeto para detecção de inundação usando produtos Sentinel-1 (SAR) e Sentinel-2 (óptico).

## Visão geral
- `S1/` — pipelines e workflows SNAP (GPT) para pré-processamento e máscara de inundação (gera `.dim` e `floodImage*.tif`).
- `S2/` — pipeline NDWI baseado em `rasterio` que gera `flood.tif` em `S2/output/`.
- `main.py` — CLI unificada para executar S1 e S2.
- `processors.py` — interfaces `Processor` para modularidade e testabilidade.

## Instalação Rápida

### Opção 1: Local (Recomendado)
```bash
# Criar ambiente Python
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/macOS

# Instalar dependências
pip install -r requirements.txt
pip install -e .  # Entry-point instalável
```

Depois você pode usar o comando `sar-msi` diretamente (se instalou entry-point):
```bash
sar-msi --use-s1 --run --view
sar-msi --use-s2 --preview
```

---

# Installation & Setup Guide

## Quick Start

### 1. Python Setup
```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode with entry-point
pip install -e .
```

After this, you can run the tool directly from anywhere:
```bash
# If you installed the package entry-point (optional)
sar-msi --use-s1 --run
sar-msi --use-s2 --preview
```

### 2. SNAP Installation (Required for Sentinel-1)

#### Windows

**Option A: ESA SNAP Installer (Recommended)**
1. Download ESA SNAP from [http://step.esa.int/main/download/](http://step.esa.int/main/download/)
2. Install to default location: `C:\Program Files\esa-snap`
3. Add to `.env` (copy from `.env.example`):
   ```
   SNAP_DIRECTORY=C:\Program Files\esa-snap
   ```

**Option B: Manual location**
If SNAP is installed elsewhere, point `.env` to the folder containing `bin\gpt.exe`:
```
SNAP_DIRECTORY=C:\Users\YourName\snap
```

#### Linux
```bash
# Download and install SNAP
wget https://download.esa.int/esaup/sentinel/SNAP/esa-snap_all_linux-x86_64.tar.gz
tar -xzf esa-snap_all_linux-x86_64.tar.gz

# Set in .env
SNAP_DIRECTORY=/path/to/snap
```

#### macOS
```bash
# Download ESA SNAP DMG from
# http://step.esa.int/main/download/

# Or via Homebrew (if available)
brew install snap
```

## Verify Installation

### Check Python Environment
```bash
python --version
pip list | grep -E "rasterio|numpy|python-dotenv"
```

### Check SNAP (if installed locally)
```bash
# Windows
"C:\Program Files\esa-snap\bin\gpt.exe" -v

# Linux/macOS
/path/to/snap/bin/gpt -v
```

### Run Tests
```bash
python -m pytest -v
```

## Troubleshooting

**Issue**: `SNAP_DIRECTORY environment variable is not set`
- **Solution**: Create `.env` file in project root with:
  ```
  SNAP_DIRECTORY=C:\Program Files\esa-snap
  ```

**Issue**: `No Sentinel-1 products found in data/`
- **Solution**: Place `.SAFE` or `.zip` Sentinel-1 products in `S1/data/products/`

**Issue**: `No B03/B08 10m pairs found`
- **Solution**: Place Sentinel-2 `.SAFE` folders in `downloads/` directory

## Development Workflow

1. **Run tests** before committing:
   ```bash
   python -m pytest -v
   ```

2. **Code formatting** (optional, recommended):
   ```bash
   pip install black isort
   black main.py processors.py S1/ S2/
   ```

3. **Type checking** (optional):
   ```bash
   pip install mypy
   mypy main.py processors.py
   ```
