# SAR-MSI Flood Detection

Flood detection project using Sentinel-1 (SAR) and Sentinel-2 (multispectral) products.

## Overview

### Project Structure
- **`Acquisition/`** — Download and management of Sentinel-1 and Sentinel-2 products via ESA Copernicus APIs
- **`app/`** — Graphical User Interface (GUI) built with CTK (CustomTkinter)
- **`Combined/`** — Combination of S1 and S2 results
- **`common/`** — Shared methods and classes used across multiple files
- **`processorsImpl/`** — Interface for the implementation of Sentinel-1 and Sentinel-2 processors
- **`S1/`** — SAR processing (Sentinel-1) using SNAP (GPT) workflows for pre-processing and flood masking
- **`S2/`** — Multispectral processing (Sentinel-2) using an NDWI pipeline based on `rasterio`
- **`main.py`** — Unified CLI for data processing
- **`app.py`** — Application interface for system interaction
- **`mainconfig.py`** — Centralized project configuration

## Detailed Directory Structure

```
SAR-MSI-FloodDetection/
├── Acquisition/          # Sentinel products download and management
│   ├── acquireProducts.py
│   ├── modules/
│   │   ├── aclasses.py
│   │   ├── acquisition_config.py
│   │   ├── authsession.py
│   │   ├── download.py
│   │   ├── regiongeocoding.py
│   │   ├── regiontimestamp.py
│   │   ├── request.py
│   │   ├── search_log.py
│   │   └── utils.py
│   └── search_log.csv
├── common/               # Shared methods/classes
│   ├── shared_config.py
│   ├── shared_models.py
│   └── shared_paths.py
├── processorsImpl/       # S1 and S2 Processor logic
│   ├── processorBase.py
│   ├── S1Processor.py
│   └── S2Processor.py
├── S1/                   # Sentinel-1 (SAR) processing
│   ├── Processing/
│   │   ├── modules/
│   │   │   ├── discovery.py
│   │   │   ├── masking.py
│   │   │   ├── paths.py
│   │   │   ├── pclasses.py
│   │   │   ├── pipeline_utils.py
│   │   │   ├── pipeline.py
│   │   │   ├── product_utils.py
│   │   │   ├── s1processing_config.py
│   │   │   ├── snap.py
│   │   │   └── utils.py
│   │   ├── processing.py
│   │   └── workflows/
│   └── output/           # Output results (*_flood.dim)
├── S2/                   # Sentinel-2 (multispectral) processing
│   ├── config.py
│   ├── discovery.py
│   ├── pclasses.py
│   ├── pipeline.py
│   ├── preview.py
│   ├── processing.py
│   ├── raster_io.py
│   ├── raster_io.py
│   └── output/           # Output results (*_flood.tif)
├── Combined/             # Combination of S1 + S2 results
│   └── combine.py
├── app/                  # Graphical User Interface (CustomTkinter)
│   ├── config.py
│   ├── ctkapp.py
│   ├── runner.py
│   ├── streams.py
│   └── ui_builder.py
├── downloads/            # Input data storage
├── tests/                # Unit tests
├── main.py               # Main CLI
├── app.py                # Graphical interface
├── mainconfig.py         # Centralized configuration
└── requirements.txt      # Python dependencies
```

## Quick Installation

### Python Setup
```bash
# Create Python environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate.bat

# Activate (Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### SNAP Installation (Required for Sentinel-1)

#### Windows

**Option A: ESA SNAP Installer (Recommended)**
1. Download ESA SNAP from [https://step.esa.int/main/download/snap-download/](https://step.esa.int/main/download/snap-download/)
2. Install in the default location: `C:\Program Files\esa-snap`
3. Add to `.env` (copy from `.env.example`):
	```
	SNAP_DIRECTORY=C:\Program Files\esa-snap
	```

**Option B: Custom location**
If SNAP is installed in another location, point `.env` to the folder containing `bin\gpt.exe`:
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

## Credentials Configuration

To download satellite data (Sentinel-1 and Sentinel-2), you need to configure authentication credentials. 
Create a `.env` file in the project root (copy `.env.example` and fill in the values):

### 1. Copernicus Data Space Ecosystem (CDSE) Credentials

1. Access https://dataspace.copernicus.eu/
2. Click on **"Register"** or **"Sign In"** if you already have an account
3. After logging in, navigate to the "Account Settings" or "User Profile" section
4. Copy your **username** and create/copy your **password**
5. Add to your `.env` file:
	```
	CDSE_USERNAME=your-username
	CDSE_PASSWORD=your-password
	```

### 2. Sentinel Hub Credentials

1. Access https://shapps.dataspace.copernicus.eu/dashboard/#/
2. Log in with your CDSE credentials
3. Navigate to **"API Keys"** or **"OAuth Clients"**
4. Create a new OAuth client:
	- Click on **"Create new"** or **"New OAuth Client"**
	- Set a name (ex: "SAR-MSI-FloodDetection")
	- Type: **"Public"** or **"Confidential"** (recomendado: Confidential)
5. Copy:
	- **Client ID** → `SH_CLIENT_ID`
	- **Client Secret** → `SH_CLIENT_SECRET`
6. Add to your `.env` file:
	```
	SH_CLIENT_ID=seu-client-id
	SH_CLIENT_SECRET=seu-client-secret
	```

## Usage

### Graphical User Interface (GUI)
```bash
python app.py
```

### Command Line Interface (CLI)
```bash
python main.py
```

## Verificar Instalação

### Verificar Ambiente Python
```bash
python --version
pip install -r requirements.txt
```

### Verify SNAP
```bash
# Windows 

# (command prompt [cmd])
"C:\Program Files\esa-snap\bin\gpt.exe" --diag
# Powershell
& "C:\Program Files\esa-snap\bin\gpt.exe" --diag

# Linux
/path/to/snap/bin/gpt --diag
```

### Run Tests
```bash
python -m pytest -v
```