#!/bin/bash

# CSExpert Environment Setup Script
# This script sets up the complete development environment for CSExpert

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Header
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   CSExpert Environment Setup Script    ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if running from project root
if [ ! -f "backend/app.py" ]; then
    print_error "Please run this script from the CSExpert project root directory"
    exit 1
fi

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="mac"
else
    print_error "Unsupported operating system: $OSTYPE"
    exit 1
fi

print_info "Detected OS: $OS"

# Check Python version
print_info "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.10"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
    print_error "Python 3.10 or higher is required. Found: $PYTHON_VERSION"
    exit 1
fi
print_success "Python $PYTHON_VERSION found"

# Install system dependencies
print_info "Installing system dependencies..."

if [ "$OS" == "linux" ]; then
    # Update package list
    sudo apt-get update -qq
    
    # Install Chrome if not present
    if ! command -v google-chrome &> /dev/null; then
        print_info "Installing Google Chrome..."
        wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
        sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list'
        sudo apt-get update -qq
        sudo apt-get install -y google-chrome-stable
        print_success "Google Chrome installed"
    else
        print_success "Google Chrome already installed"
    fi
    
    # Install other dependencies
    sudo apt-get install -y python3-pip python3-venv git wget curl
    
elif [ "$OS" == "mac" ]; then
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        print_error "Homebrew is required. Please install it from https://brew.sh"
        exit 1
    fi
    
    # Install Chrome if not present
    if ! [ -d "/Applications/Google Chrome.app" ]; then
        print_info "Installing Google Chrome..."
        brew install --cask google-chrome
        print_success "Google Chrome installed"
    else
        print_success "Google Chrome already installed"
    fi
fi

# Create virtual environment
print_info "Creating virtual environment..."
if [ -d "venv" ]; then
    print_warning "Virtual environment already exists. Recreating..."
    rm -rf venv
fi

python3 -m venv venv
print_success "Virtual environment created"

# Activate virtual environment
print_info "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
print_info "Upgrading pip..."
pip install --upgrade pip wheel setuptools

# Install Python packages
print_info "Installing Python packages..."

# Create comprehensive requirements.txt
cat > requirements_complete.txt << 'EOF'
# Core Web Framework
fastapi==0.116.1
uvicorn[standard]==0.35.0
python-multipart==0.0.20
fastapi-cors==0.0.6

# Database
SQLAlchemy==2.0.41

# LangChain and AI
langchain==0.3.26
langchain-core==0.3.69
langchain-community==0.3.27
langchain-google-genai==2.0.10
langchain-google-vertexai==2.0.27
langchain-chroma==0.2.4
google-generativeai==0.8.5
google-cloud-aiplatform==1.104.0

# Vector Database
chromadb==1.0.15

# Web Scraping
selenium==4.34.2
webdriver-manager==4.0.2
beautifulsoup4==4.13.4
requests==2.32.4
tldextract==5.3.0

# PDF Processing
PyPDF2==3.0.1

# Data Processing
numpy==2.3.1
pandas==2.2.3

# Utilities
python-dotenv==1.1.1
pydantic==2.11.7
pydantic-settings==2.10.1
tqdm==4.67.1
click==8.2.1
colorama==0.4.6
PyYAML==6.0.2

# Development Tools
pytest==8.3.3
pytest-asyncio==0.24.0
black==24.10.0
flake8==7.1.1
mypy==1.13.0
EOF

# Install all packages
pip install -r requirements_complete.txt

print_success "Python packages installed"

# Create necessary directories
print_info "Creating project directories..."
mkdir -p data/syllabi_pdfs
mkdir -p data/syllabi_pages  
mkdir -p data/course_pages
mkdir -p data/programs
mkdir -p logs
mkdir -p temp

print_success "Directories created"

# Create .env template if it doesn't exist
if [ ! -f ".env" ]; then
    print_info "Creating .env template..."
    cat > .env.template << 'EOF'
# Google Gemini API Configuration
GEMINI_API_KEY=your-gemini-api-key-here

# Database Configuration
DATABASE_PATH=data/csexpert.db

# Logging Configuration
LOG_LEVEL=INFO

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# CORS Configuration
CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"]

# Scraper Configuration
MAX_CONCURRENT_DOWNLOADS=6
MAX_CONCURRENT_SCRAPERS=6
GEMINI_DELAY=0.06  # For Tier 1 (1000 RPM)
EOF
    
    print_success ".env.template created"
    print_warning "Please copy .env.template to .env and add your API keys"
else
    print_success ".env file already exists"
fi

# Initialize database
print_info "Initializing database..."
python -c "
from database.database_initializer import DatabaseInitializer
initializer = DatabaseInitializer('data/csexpert.db')
if initializer.initialize_database():
    print('Database initialized successfully')
else:
    print('Database initialization failed')
    exit(1)
"

# Run tests to verify installation
print_info "Running verification tests..."
python -c "
import sys
try:
    import fastapi
    import sqlalchemy
    import langchain
    import chromadb
    import selenium
    import bs4
    import PyPDF2
    import google.generativeai
    print('All core packages imported successfully')
except ImportError as e:
    print(f'Import error: {e}')
    sys.exit(1)
"

# Create activation script
print_info "Creating activation helper..."
cat > activate.sh << 'EOF'
#!/bin/bash
# Quick activation script for CSExpert environment

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "CSExpert environment activated"
    echo "Python: $(which python)"
    echo "Version: $(python --version)"
else
    echo "Virtual environment not found. Run ./setup.sh first"
fi
EOF
chmod +x activate.sh

# Final summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}    Setup completed successfully!       ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Copy .env.template to .env and add your API keys"
echo "2. Activate the environment: source venv/bin/activate"
echo "   Or use the helper: ./activate.sh"
echo "3. Run the backend: python backend/app.py"
echo "4. Run the scraper: python -m scraper.database_scraper_orchestrator"
echo ""
print_info "For frontend setup, see frontend/README.md"

# Save the complete requirements for future use
mv requirements_complete.txt requirements.txt
print_success "Updated requirements.txt with all packages"