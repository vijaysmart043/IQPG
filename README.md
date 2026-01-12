# Intelligent EXAM Generation System

A comprehensive Flask-based web application for automated university-level examination question paper creation with AI and blockchain security.

## ✨ Features

- **Admin Authentication**: Secure login using Firebase Authentication
- **Academic Management**: Add and manage branches and subjects
- **AI Question Generation**: Upload PDF notes → Automatic text extraction → AI generates questions
- **Free AI**: Uses Ollama (local, no API costs) instead of expensive OpenAI
- **Bloom's Taxonomy**: Questions classified into cognitive levels (L1-L6)
- **Staging Workflow**: Review, approve, or reject AI-generated questions
- **Blockchain Security**: Immutable question bank with hash chains in Firestore
- **Paper Generation**: Create formatted exam papers with fuzzy logic selection

## 🚀 Quick Start (Windows)

### 1. Install Ollama (Free AI)
```bash
# Download from: https://ollama.ai/download/windows
# Install and run Ollama
```

### 2. Download AI Model
```bash
ollama pull llama3.2:3b-instruct  # Fast model (recommended)
# OR for better quality (slower):
ollama pull llama3.1:8b-instruct
```

### 3. Start the System
```bash
# Double-click start.bat OR run:
start.bat
```

### 4. Access the Application
- Open: http://localhost:5000
- Login with admin credentials
- Upload PDFs and generate questions!

## 🔧 Manual Setup (Alternative)

If `start.bat` doesn't work:

### Terminal 1: Start Ollama
```bash
ollama serve
```

### Terminal 2: Start Flask
```bash
python app.py
```

PDF Export: Exports the final question paper as a professional-grade PDF using ReportLab, complete with a university-style header.

Blockchain Integrity Check: A feature on the admin dashboard allows for on-demand verification of the blockchain's integrity.

Project Structure
/question-paper-generator
|-- /routes
|   |-- admin.py
|   |-- generator.py
|   |-- management.py
|   `-- questions.py
|-- /templates
|   |-- branches.html
|   |-- dashboard.html
|   |-- generate_paper.html
|   |-- login.html
|   |-- staging.html
|   |-- subjects.html
|   `-- upload_notes.html
|-- .env
|-- app.py
|-- blockchain.py
|-- firebase_config.py
|-- README.md
`-- requirements.txt

Setup and Installation
Clone/Download the Repository: Place all the project files into a single directory named question-paper-generator.

Create a Virtual Environment:

python -m venv venv

Activate the Virtual Environment:

Windows: venv\Scripts\activate

macOS/Linux: source venv/bin/activate

Install Dependencies: Install all required packages using the requirements.txt file.

pip install -r requirements.txt

Configure Environment Variables:

Make sure the .env file is in the root directory.

Ensure your Firebase serviceAccountKey.json is at the path specified in the .env file.

How to Run the Application
Make sure your virtual environment is activated.

Use the Flask CLI to run the development server:

flask run

Open your web browser and navigate to:
http://127.0.0.1:5000/admin/login

You can now log in and start using the application.
---
Local open-source LLM (optional): Ollama
If you want free local AI generation instead of OpenAI, enable Ollama:

1) Install Ollama (Windows/macOS/Linux): https://ollama.com/download
2) Pull a model (recommended):

ollama pull llama3.1:8b-instruct

3) In .env set:

OLLAMA_ENABLED=1
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b-instruct

4) Restart the Flask server. The upload-notes flow and the syllabus generator will now use the local model (strict JSON output) for question generation.
