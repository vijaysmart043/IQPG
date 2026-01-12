from flask import Blueprint, render_template, session, redirect, url_for, flash, request, current_app
from functools import wraps
import os
import json
import re
from io import BytesIO
from pdfminer.high_level import extract_text
from firebase_config import db

from routes.bloom_rag_controller import (
    get_controller,
    BLOOM_LEVELS
)

mcq_bp = Blueprint("mcq", __name__)

def login_required(f):
    """
    Decorator to ensure a user is logged in before accessing a route.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function

def _get_cohere_key():
    """Get Cohere API key from environment."""
    return os.getenv("COHERE_API_KEY")

def _is_ai_available():
    """Check if AI service (Cohere) is available."""
    return bool(_get_cohere_key())


@mcq_bp.route("/generator", methods=['GET', 'POST'])
@login_required
def generator():
    if request.method == 'POST':
        cohere_key = _get_cohere_key()
        if not cohere_key:
            flash("COHERE_API_KEY is not configured. Please set it in your .env file.", "danger")
            return redirect(request.url)
        
        if 'mcq_file' not in request.files:
            flash("No file part in the request.", "danger")
            return redirect(request.url)

        file = request.files['mcq_file']
        if file.filename == '':
            flash("No file selected.", "danger")
            return redirect(request.url)

        if file and file.filename.endswith('.pdf'):
            try:
                # Extract text from PDF
                file_content = file.read()
                pdf_file = BytesIO(file_content)
                extracted_text = extract_text(pdf_file)
                
                # Clean text
                extracted_text = re.sub(r'\n+', ' ', extracted_text)
                extracted_text = re.sub(r'\s+', ' ', extracted_text)
                extracted_text = extracted_text.strip()
                
                if len(extracted_text) < 100:
                    flash("PDF contains very little text to analyze. Please ensure the PDF has sufficient content.", "warning")
                    return redirect(request.url)

                # Generate MCQs using Cohere via Bloom RAG Controller
                controller = get_controller(cohere_key)
                chunks = controller.chunk_text(extracted_text, max_chars=2000)
                
                generated_mcqs = []
                bloom_levels = ["Remember", "Understand", "Apply"]
                
                # Generate questions for each chunk (up to 50 questions)
                max_questions = min(50, len(chunks) * 3)
                questions_per_chunk = max(1, max_questions // len(chunks)) if chunks else 0
                
                for i, chunk in enumerate(chunks):
                    if len(generated_mcqs) >= max_questions:
                        break
                    
                    for j in range(questions_per_chunk):
                        if len(generated_mcqs) >= max_questions:
                            break
                        
                        bloom_level = bloom_levels[(i + j) % len(bloom_levels)]
                        try:
                            question = controller.generate_question_for_chunk(chunk, bloom_level)
                            generated_mcqs.append({
                                "question": question,
                                "options": {
                                    "A": "Option A - Please update",
                                    "B": "Option B - Please update",
                                    "C": "Option C - Please update",
                                    "D": "Option D - Please update"
                                },
                                "correct_answer": "A",
                                "note": f"Generated at {bloom_level} level. Please update options and correct answer."
                            })
                        except Exception as e:
                            current_app.logger.error(f"Error generating MCQ for chunk {i}: {e}")
                            continue
                
                if not generated_mcqs:
                    flash("Could not generate any MCQs from the PDF. Please try with different content.", "warning")
                else:
                    flash(f"Generated {len(generated_mcqs)} questions using Cohere. Please update options and correct answers manually.", "success")
                
                return render_template('mcq_generator.html', generated_mcqs=generated_mcqs)

            except Exception as e:
                current_app.logger.error(f"Error during file processing or AI generation: {e}")
                flash(f"An error occurred: {e}", "danger")
            
            return redirect(url_for('mcq.generator'))

    return render_template("mcq_generator.html")
