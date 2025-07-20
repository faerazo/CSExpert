# CSExpert Setup Guide

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/CSExpert.git
   cd CSExpert
   ```

2. **Run the setup script**
   ```bash
   ./setup.sh
   ```

   This script will:
   - Check Python version (requires 3.10+)
   - Install system dependencies (Google Chrome, etc.)
   - Create a virtual environment
   - Install all Python packages
   - Create necessary directories
   - Initialize the database
   - Create a .env template

3. **Configure environment variables**
   ```bash
   cp .env.template .env
   # Edit .env and add your Gemini API key
   ```

4. **Activate the environment**
   ```bash
   source venv/bin/activate
   # or use the helper script:
   ./activate.sh
   ```

## Manual Setup (Alternative)

If you prefer to set up manually or the script fails:

### 1. System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv google-chrome-stable
```

**macOS:**
```bash
brew install python@3.10
brew install --cask google-chrome
```

### 2. Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install packages
pip install -r requirements.txt
```

### 3. Database Setup

```bash
python -c "from database.database_initializer import DatabaseInitializer; DatabaseInitializer().initialize_database()"
```

### 4. Environment Variables

Create a `.env` file:
```env
GEMINI_API_KEY=your-api-key-here
DATABASE_PATH=data/csexpert.db
LOG_LEVEL=INFO
```

## Verification

Test your installation:
```bash
# Check Python packages
python -c "import fastapi, sqlalchemy, langchain, selenium; print('All packages OK')"

# Check database
python -c "from database.connection_manager import get_database_manager; print('Database OK')"

# Run tests
python -m pytest tests/
```

## Troubleshooting

### Chrome/ChromeDriver Issues
```bash
# Clear driver cache
rm -rf ~/.wdm/

# Reinstall Chrome
sudo apt-get remove google-chrome-stable
sudo apt-get install google-chrome-stable
```

### Permission Errors
```bash
# Fix script permissions
chmod +x setup.sh activate.sh

# Fix directory permissions
chmod -R 755 data/
```

### Virtual Environment Issues
```bash
# Remove and recreate
rm -rf venv/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Next Steps

1. **Run the backend API:**
   ```bash
   python backend/app.py
   ```

2. **Run the scraper:**
   ```bash
   python -m scraper.database_scraper_orchestrator
   ```

3. **Set up the frontend:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Development Tips

- Always activate the virtual environment before working
- Keep your Gemini API key secure (never commit .env)
- Run the scraper during off-peak hours to avoid rate limits
- Backup the database regularly: `cp data/csexpert.db data/csexpert.db.backup`