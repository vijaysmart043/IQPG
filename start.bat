@echo off
echo 🚀 Starting Intelligent EXAM Generation System...
echo.

echo 🔧 Checking Ollama status...
ollama list >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Ollama not found. Please install Ollama first.
    echo Download from: https://ollama.ai/download/windows
    pause
    exit /b 1
)

echo ✅ Ollama found!

echo 🔄 Starting Ollama server in background...
start /B ollama serve

echo ⏳ Waiting for Ollama to start...
timeout /t 5 /nobreak >nul

echo 📚 Checking available models...
ollama list

echo 🐍 Starting Flask application...
python app.py