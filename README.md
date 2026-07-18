# SAR-MSI Flood Detection

Projeto para deteção de inundação usando produtos Sentinel-1 (SAR) e Sentinel-2 (multiespetral).

## Visão geral

### Estrutura do Projeto
- **`Acquisition/`** — Download e gestão de produtos Sentinel-1 e Sentinel-2 via APIs ESA Copernicus
- **`S1/`** — Processamento SAR (Sentinel-1) com workflows SNAP (GPT) para pré-processamento e máscara de inundação
- **`S2/`** — Processamento óptico (Sentinel-2) com pipeline NDWI baseado em `rasterio`
- **`Combined/`** — Combinação de resultados S1 e S2
- **`app/`** — Interface gráfica (GUI) com CTK (CustomTkinter)
- **`main.py`** — CLI unificada para processar dados
- **`interface.py`** — Interface para interação com o sistema
- **`mainconfig.py`** — Configuração centralizada do projeto
- **`processors.py`** — Interfaces base para processadores (modularidade e testabilidade)

## Estrutura de Diretórios Detalhada

```
SAR-MSI-FloodDetection/
├── Acquisition/          # Download e gestão de produtos Sentinel
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
│   └── search_log.csv~
├── common/               # Metodos/Classes em comum
│   ├── shared_config.py
│   ├── shared_models.py
│   └── shared_paths.py
├── processorsImpl/       # Logica dos Processadores S1 e S2
│   ├── processorBase.py
│   ├── S1Processor.py
│   └── S2Processor.py
├── S1/                   # Processamento Sentinel-1 (SAR)
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
│   └── output/           # Resultados (flood_*.dim)
├── S2/                   # Processamento Sentinel-2 (óptico)
│   ├── config.py
│   ├── discovery.py
│   ├── pclasses.py
│   ├── pipeline.py
│   ├── preview.py
│   ├── processing.py
│   ├── raster_io.py
│   ├── raster_io.py
│   └── output/           # Resultados (flood.tif)
├── Combined/             # Combinação de resultados S1 + S2
│   └── combine.py
├── app/                  # Interface gráfica (CustomTkinter)
│   ├── config.py
│   ├── ctkapp.py
│   ├── runner.py
│   ├── streams.py
│   └── ui_builder.py
├── downloads/            # Armazenamento de dados de entrada
├── tests/                # Testes unitários
├── main.py               # CLI principal
├── app.py                # Interface gráfica
├── mainconfig.py         # Configuração centralizada
└── requirements.txt      # Dependências Python
```

## Instalação Rápida

### Python Setup
```bash
# Criar ambiente Python
python -m venv .venv

# Ativar (Windows)
.venv\Scripts\activate.bat

# Ativar (Linux)
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

### SNAP Installation (Obrigatório para Sentinel-1)

#### Windows

**Opção A: ESA SNAP Installer (Recomendado)**
1. Download ESA SNAP de [https://step.esa.int/main/download/snap-download/](https://step.esa.int/main/download/snap-download/)
2. Instalar no local padrão: `C:\Program Files\esa-snap`
3. Adicionar a `.env` (copiar de `.env.example`):
	```
	SNAP_DIRECTORY=C:\Program Files\esa-snap
	```

**Opção B: Localização manual**
Se SNAP está instalado noutro local, apontar `.env` para a pasta contendo `bin\gpt.exe`:
```
SNAP_DIRECTORY=C:\Users\YourName\snap
```

#### Linux
```bash
# Download e instalar SNAP
wget https://download.esa.int/esaup/sentinel/SNAP/esa-snap_all_linux-x86_64.tar.gz
tar -xzf esa-snap_all_linux-x86_64.tar.gz

# Definir em .env
SNAP_DIRECTORY=/path/to/snap
```

## Configuração de Credenciais

Para descarregar dados de satélite (Sentinel-1 e Sentinel-2), é necessário configurar credenciais de autenticação. Crie um ficheiro `.env` na raiz do projeto (copie `.env.example` e preencha os valores):

### 1. Credenciais Copernicus Data Space Ecosystem (CDSE)

1. Aceda a https://dataspace.copernicus.eu/
2. Clique em **"Register"** ou **"Sign In"** se já tem conta
3. Após login, navegue para a secção de "Account Settings" ou "User Profile"
4. Copie o seu **username** e crie/copie a sua **password**
5. Adicione ao `.env`:
	```
	CDSE_USERNAME=seu-username
	CDSE_PASSWORD=sua-password
	```

### 2. Credenciais Sentinel Hub

1. Aceda a https://shapps.dataspace.copernicus.eu/dashboard/#/
2. Faça login com as suas credenciais CDSE
3. Navegue para **"API Keys"** ou **"OAuth Clients"**
4. Crie um novo cliente OAuth:
	- Clique em **"Create new"** ou **"New OAuth Client"**
	- Defina um nome (ex: "SAR-MSI-FloodDetection")
	- Tipo: **"Public"** ou **"Confidential"** (recomendado: Confidential)
5. Copie:
	- **Client ID** → `SH_CLIENT_ID`
	- **Client Secret** → `SH_CLIENT_SECRET`
6. Adicione ao `.env`:
	```
	SH_CLIENT_ID=seu-client-id
	SH_CLIENT_SECRET=seu-client-secret
	```

## Uso

### Interface Gráfica (GUI)
```bash
python interface.py
```

### Linha de Comando (CLI)
```bash
python main.py
```

## Verificar Instalação

### Verificar Ambiente Python
```bash
python --version
pip list | grep -E "rasterio|numpy|python-dotenv"
```

### Verificar SNAP (se instalado localmente)
```bash
# Windows
"C:\Program Files\esa-snap\bin\gpt.exe" -v

# Linux
/path/to/snap/bin/gpt -v
```

### Executar Testes
```bash
python -m pytest -v
```

## Resolução de Problemas

**Problema**: `SNAP_DIRECTORY environment variable is not set`
- **Solução**: Criar ficheiro `.env` na raiz do projeto com:
  ```
  SNAP_DIRECTORY=C:\Program Files\esa-snap
  ```