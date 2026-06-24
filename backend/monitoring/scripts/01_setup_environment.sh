#!/bin/bash
# ============================================================
# STEP 1: ENVIRONMENT SETUP
# File: scripts/01_setup_environment.sh
# Run: chmod +x scripts/01_setup_environment.sh && sudo ./scripts/01_setup_environment.sh
# ============================================================

set -e
echo "============================================"
echo "  SecurePrint AI — Environment Setup"
echo "============================================"

# ---- 1.1 System Update ----
echo "[1.1] Updating system packages..."
apt-get update -y && apt-get upgrade -y

# ---- 1.2 Install Core Dependencies ----
echo "[1.2] Installing core dependencies..."
apt-get install -y \
    python3.11 python3.11-venv python3-pip \
    docker.io docker-compose \
    git curl wget unzip \
    build-essential cmake libssl-dev \
    nodejs npm \
    nginx \
    postgresql postgresql-contrib \
    redis-server \
    ffmpeg libsm6 libxext6 libxrender-dev \
    tesseract-ocr

# ---- 1.3 Install CUDA (if NVIDIA GPU present) ----
echo "[1.3] Checking for NVIDIA GPU..."
if command -v nvidia-smi &> /dev/null; then
    echo "GPU detected — installing CUDA toolkit..."
    apt-get install -y nvidia-cuda-toolkit
else
    echo "No GPU detected — using CPU-only mode"
fi

# ---- 1.4 Setup Python Virtual Environment ----
echo "[1.4] Creating Python virtual environment..."
python3.11 -m venv /opt/secureprint-venv
source /opt/secureprint-venv/bin/activate

# ---- 1.5 Install Python ML/AI Libraries ----
echo "[1.5] Installing Python libraries..."
pip install --upgrade pip
pip install \
    tensorflow==2.15.0 \
    torch torchvision torchaudio \
    opencv-python-headless==4.9.0.80 \
    ultralytics \
    scikit-learn \
    numpy pandas matplotlib seaborn \
    Pillow \
    flask flask-restx flask-jwt-extended flask-cors \
    sqlalchemy alembic psycopg2-binary \
    redis celery \
    cryptography pycryptodome \
    web3 \
    hashlib \
    boto3 \
    prometheus-client \
    pyyaml python-dotenv \
    pytest pytest-cov \
    bandit safety \
    gunicorn

# ---- 1.6 Install Docker & Enable Service ----
echo "[1.6] Configuring Docker..."
systemctl enable docker
systemctl start docker
usermod -aG docker $USER

# ---- 1.7 Install Hyperledger Fabric Prerequisites ----
echo "[1.7] Installing Hyperledger Fabric prerequisites..."
curl -sSL https://bit.ly/2ysbOFE | bash -s -- 2.5.0 1.5.7

# ---- 1.8 Setup PostgreSQL Database ----
echo "[1.8] Configuring PostgreSQL..."
sudo -u postgres psql <<EOF
CREATE USER secureprint WITH PASSWORD 'SecurePrint@2024!';
CREATE DATABASE secureprint_db OWNER secureprint;
GRANT ALL PRIVILEGES ON DATABASE secureprint_db TO secureprint;
EOF

# ---- 1.9 Setup Redis ----
echo "[1.9] Configuring Redis..."
systemctl enable redis-server
systemctl start redis-server

# ---- 1.10 Create Project Directory Structure ----
echo "[1.10] Creating project structure..."
mkdir -p /opt/secureprint/{
    models/{defect_detection,anomaly,classification},
    data/{training,validation,test,uploads},
    blockchain/{chaincode,network},
    certs,
    logs,
    uploads/{designs,prints},
    keys
}

chmod 700 /opt/secureprint/keys
chmod 700 /opt/secureprint/certs

echo ""
echo "============================================"
echo "  ✅ STEP 1 COMPLETE: Environment Ready"
echo "============================================"
echo ""
echo "Next: Run python scripts/02_train_defect_model.py"
