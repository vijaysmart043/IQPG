# Gemini AI Setup Instructions

## Getting Your Google API Key

1. **Go to Google AI Studio**: Visit https://makersuite.google.com/app/apikey
2. **Sign in** with your Google account
3. **Create a new API key** by clicking "Create API Key"
4. **Copy the API key** (it will look like: `AIzaSy...`)

## Configure Your Application

1. **Open the `.env` file** in your project root
2. **Add your Google API key**:
   ```
   GOOGLE_API_KEY="your-actual-api-key-here"
   ```
3. **Save the file**

## How It Works

The uploader.py route uses Google's Gemini AI to:
- Extract text from uploaded PDF files
- Analyze the content using advanced AI
- Generate 5 high-quality exam questions with:
  - Two sub-questions (a and b) for each question
  - Bloom's Taxonomy classification (L1-L5)
  - Unit assignment (1-5)
  - JNTUK-style question format

## Features

- **PDF Text Extraction**: Uses PyMuPDF for reliable text extraction
- **AI Question Generation**: Gemini AI analyzes content and generates questions
- **Staging System**: Questions go to staging area for admin review
- **Quality Control**: Admin can approve, reject, or edit generated questions
- **Firestore Integration**: All data stored securely in Firebase

## Usage

1. **Login** to the admin dashboard
2. **Go to "AI Question Generation"** card
3. **Select a subject** from the dropdown
4. **Upload a PDF** with course notes
5. **Click "Upload & Start Generation"**
6. **Wait for processing** (may take 1-2 minutes)
7. **Review generated questions** in the staging area

## Troubleshooting

- **"AI Model is not configured"**: Check your GOOGLE_API_KEY in .env file
- **"Failed to parse AI response"**: The AI response wasn't in the expected JSON format
- **"PDF contains very little text"**: The PDF might be image-based or corrupted

## API Limits

- Gemini API has rate limits and usage quotas
- Large PDFs are automatically truncated to 10,000 characters
- Processing time depends on PDF size and complexity
