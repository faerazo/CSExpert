#!/bin/bash

# CSExpert Development Setup Script (Python packages only)
# For developers who already have system dependencies installed

set -e

echo "CSExpert Dev Setup - Python packages only"
echo "========================================="

# Check if in project root
if [ ! -f "backend/app.py" ]; then
    echo "Error: Run this script from the project root"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip wheel setuptools

# Install packages
echo "Installing Python packages..."
pip install -r requirements.txt

# Create directories
echo "Creating directories..."
mkdir -p data/{syllabi_pdfs,syllabi_pages,course_pages,programs} logs temp

# Initialize database
echo "Initializing database..."
python -c "
try:
    from database.database_initializer import DatabaseInitializer
    if DatabaseInitializer().initialize_database():
        print('✓ Database initialized')
    else:
        print('✗ Database initialization failed')
except Exception as e:
    print(f'✗ Error: {e}')
"

# Create .env template
if [ ! -f ".env" ]; then
    echo "Creating .env template..."
    echo "GEMINI_API_KEY=your-api-key-here" > .env.template
    echo "✓ Created .env.template"
fi

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy .env.template to .env and add your API key"
echo "2. Activate environment: source venv/bin/activate"
echo "3. Run backend: python backend/app.py"