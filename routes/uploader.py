import os
import json
import re
from io import BytesIO
from flask import Blueprint, request, render_template, redirect, url_for, flash, current_app, session, jsonify, Response
from firebase_config import db
from datetime import datetime
from functools import wraps
from pdfminer.high_level import extract_text
from pypdf import PdfReader

from routes.bloom_rag_controller import (
    BloomRAGController, 
    get_controller, 
    validate_bloom_level, 
    BLOOM_LEVELS,
    RAGConfig,
    StagedQuestion,
    format_staged_questions,
    add_question_to_staging
)

# --- Blueprint Setup ---
uploader_bp = Blueprint('uploader', __name__)

# --- Login Required Decorator ---
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

# --- Check if Cohere is configured ---
def _get_cohere_key():
    """Get Cohere API key from environment."""
    return os.getenv("COHERE_API_KEY")

def _is_ai_available():
    """Check if AI service (Cohere) is available."""
    return bool(_get_cohere_key())


# --- Routes ---
@uploader_bp.route('/upload-notes', methods=['GET', 'POST'])
@login_required
def upload_notes():
    """
    Upload notes page - now uses Cohere via Bloom RAG for question generation.
    """
    cohere_key = _get_cohere_key()
    if not cohere_key:
        flash("COHERE_API_KEY is not configured. Please set it in your .env file.", "danger")
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        if not subject_id:
            flash("Please select a subject.", "danger")
            return redirect(request.url)

        if 'notes_file' not in request.files:
            flash("No file part in the request.", "danger")
            return redirect(request.url)

        file = request.files['notes_file']
        if file.filename == '':
            flash("No file selected.", "danger")
            return redirect(request.url)

        is_syllabus = 'is_syllabus' in request.form
        
        if file and file.filename.endswith('.pdf'):
            try:
                # 1. Extract text from PDF using pdfminer
                file_content = file.read()
                pdf_file = BytesIO(file_content)
                extracted_text = extract_text(pdf_file)
                
                # Clean and preprocess text
                extracted_text = re.sub(r'\n+', ' ', extracted_text)
                extracted_text = re.sub(r'\s+', ' ', extracted_text)
                extracted_text = extracted_text.strip()
                
                if len(extracted_text) < 100:
                    flash("PDF contains very little text to analyze. Please ensure the PDF has sufficient content.", "warning")
                    return redirect(request.url)

                # 2. Use Cohere via Bloom RAG Controller for question generation
                controller = get_controller(cohere_key)
                
                # Determine bloom level based on content type
                # Syllabus: Use "Understand" level, Notes: Use "Apply" level
                bloom_level = "Understand" if is_syllabus else "Apply"
                
                # Chunk and generate questions
                chunks = controller.chunk_text(extracted_text, max_chars=4000)
                current_app.logger.info(f"Splitting text into {len(chunks)} chunks for Cohere generation.")
                
                generated_questions = []
                errors = []
                
                # Process each chunk with Cohere
                for result in controller.process_text_streaming(extracted_text, bloom_level, max_chars=4000):
                    if result.success:
                        generated_questions.append({
                            "unit": (result.chunk_index % 5) + 1,
                            "question_text_a": result.question,
                            "question_text_b": "",
                            "bloom_level": BLOOM_LEVELS.index(bloom_level) + 1
                        })
                    else:
                        errors.append({
                            'chunk_index': result.chunk_index,
                            'error': result.error
                        })
                        current_app.logger.error(f"Error generating question for chunk {result.chunk_index}: {result.error}")
                
                if errors:
                    current_app.logger.warning(f"{len(errors)} chunks failed to generate questions.")
                
                # Fallback if no questions are generated
                if not generated_questions:
                    current_app.logger.warning("No questions generated, using fallback.")
                    generated_questions.append({
                        "unit": 1,
                        "question_text_a": "What are the main topics covered in the uploaded material?",
                        "question_text_b": "Explain one key concept from the material in detail.",
                        "bloom_level": 2
                    })

                # Save to staging
                staging_collection = db.collection('staging')
                saved_questions = []
                saved_count = 0
                
                for q_data in generated_questions:
                    try:
                        doc_ref = staging_collection.add({
                            'subject_id': subject_id,
                            'unit': q_data.get('unit', 1),
                            'sub_a': q_data.get('question_text_a', '').strip(),
                            'sub_b': q_data.get('question_text_b', '').strip(),
                            'bloom_level': q_data.get('bloom_level', 2),
                            'status': 'pending',
                            'created_at': datetime.utcnow(),
                            'generated_by_ai': True,
                            'source': 'syllabus_upload' if is_syllabus else 'notes_upload'
                        })
                        q_data['id'] = doc_ref[1].id
                        q_data['subject_name'] = db.collection('subjects').document(subject_id).get().to_dict().get('name', 'Unknown')
                        saved_questions.append(q_data)
                        saved_count += 1
                    except Exception as e:
                        current_app.logger.error(f"Failed to save question to Firestore: {e}")
                        continue
                
                if saved_count > 0:
                    flash(f"Successfully generated and staged {saved_count} questions using Cohere!", "success")
                    subjects_ref = db.collection('subjects').stream()
                    subjects = [{'id': s.id, **s.to_dict()} for s in subjects_ref]
                    return render_template('upload_notes.html', subjects=subjects, generated_questions=saved_questions)
                else:
                    flash("Questions were generated but could not be saved. Please try again.", "warning")

            except Exception as e:
                current_app.logger.error(f"Error during file processing or AI generation: {e}")
                flash(f"An error occurred: {e}", "danger")
            
            return redirect(url_for('uploader.upload_notes'))

    # For GET request
    subjects_ref = db.collection('subjects').stream()
    subjects = [{'id': s.id, **s.to_dict()} for s in subjects_ref]
    return render_template('upload_notes.html', subjects=subjects)


# --- Bloom's Taxonomy RAG Routes ---
@uploader_bp.route('/bloom-rag', methods=['GET', 'POST'])
@login_required
def bloom_rag_upload():
    """
    Bloom's Taxonomy RAG Question Generator page.
    Matches the exact behavior of the Streamlit app (RAG/app.py).
    """
    cohere_key = _get_cohere_key()
    if not cohere_key:
        flash("COHERE_API_KEY is not configured. Please set it in your .env file.", "danger")
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        bloom_level = request.form.get('bloom_level')
        
        if not subject_id:
            flash("Please select a subject.", "danger")
            return redirect(request.url)
        
        if not bloom_level or not validate_bloom_level(bloom_level):
            flash("Please select a valid Bloom's Taxonomy level.", "danger")
            return redirect(request.url)
        
        if 'pdf_file' not in request.files:
            flash("No file part in the request.", "danger")
            return redirect(request.url)
        
        file = request.files['pdf_file']
        if file.filename == '':
            flash("No file selected.", "danger")
            return redirect(request.url)
        
        if not file.filename.endswith('.pdf'):
            flash("Please upload a PDF file.", "danger")
            return redirect(request.url)
        
        try:
            # Extract text from PDF using PyPDF (same as Streamlit app)
            file_content = file.read()
            pdf_file = BytesIO(file_content)
            reader = PdfReader(pdf_file)
            
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            if len(text.strip()) < 50:
                flash("PDF contains very little text. Please ensure the PDF has sufficient content.", "warning")
                return redirect(request.url)
            
            # Initialize Bloom RAG Controller
            controller = get_controller(cohere_key)
            
            # Chunk text into ~4000 character segments (same as Streamlit app)
            chunks = controller.chunk_text(text, max_chars=4000)
            current_app.logger.info(f"Splitting text into {len(chunks)} chunks of ~4000 characters each.")
            
            # Process each chunk and generate questions
            generated_questions = []
            errors = []
            
            for result in controller.process_text_streaming(text, bloom_level, max_chars=4000):
                if result.success:
                    generated_questions.append({
                        'chunk_index': result.chunk_index,
                        'chunk_text': result.chunk_text[:200] + '...' if len(result.chunk_text) > 200 else result.chunk_text,
                        'question': result.question,
                        'bloom_level': bloom_level
                    })
                else:
                    errors.append({
                        'chunk_index': result.chunk_index,
                        'error': result.error
                    })
                    current_app.logger.error(f"Error generating question for chunk {result.chunk_index}: {result.error}")
            
            # Save questions to staging
            staging_collection = db.collection('staging')
            saved_count = 0
            saved_questions = []
            
            for i, q in enumerate(generated_questions):
                try:
                    doc_ref = staging_collection.add({
                        'subject_id': subject_id,
                        'unit': (i % 5) + 1,
                        'sub_a': q['question'],
                        'sub_b': '',
                        'bloom_level': BLOOM_LEVELS.index(bloom_level) + 1,
                        'status': 'pending',
                        'created_at': datetime.utcnow(),
                        'generated_by_ai': True,
                        'source': 'bloom_rag'
                    })
                    q['id'] = doc_ref[1].id
                    subject_doc = db.collection('subjects').document(subject_id).get()
                    q['subject_name'] = subject_doc.to_dict().get('name', 'Unknown') if subject_doc.exists else 'Unknown'
                    saved_questions.append(q)
                    saved_count += 1
                except Exception as e:
                    current_app.logger.error(f"Failed to save question to Firestore: {e}")
                    continue
            
            if saved_count > 0:
                flash(f"Successfully generated {saved_count} Bloom's Taxonomy questions!", "success")
            
            if errors:
                flash(f"Warning: {len(errors)} chunk(s) failed to generate questions.", "warning")
            
            # Get subjects for re-render
            subjects_ref = db.collection('subjects').stream()
            subjects = [{'id': s.id, **s.to_dict()} for s in subjects_ref]
            
            return render_template(
                'bloom_rag_upload.html',
                subjects=subjects,
                bloom_levels=BLOOM_LEVELS,
                generated_questions=saved_questions,
                errors=errors,
                extracted_text=text,
                total_chunks=len(chunks),
                selected_bloom_level=bloom_level
            )
            
        except Exception as e:
            current_app.logger.error(f"Error during Bloom RAG processing: {e}")
            flash(f"An error occurred: {e}", "danger")
            return redirect(request.url)
    
    # GET request - render the form
    subjects_ref = db.collection('subjects').stream()
    subjects = [{'id': s.id, **s.to_dict()} for s in subjects_ref]
    
    return render_template(
        'bloom_rag_upload.html',
        subjects=subjects,
        bloom_levels=BLOOM_LEVELS
    )


@uploader_bp.route('/bloom-rag/api/generate', methods=['POST'])
@login_required
def bloom_rag_api_generate():
    """
    API endpoint for Bloom RAG question generation.
    Returns JSON with generated questions.
    """
    cohere_key = _get_cohere_key()
    if not cohere_key:
        return jsonify({'error': 'COHERE_API_KEY not configured'}), 500
    
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'No PDF file provided'}), 400
    
    bloom_level = request.form.get('bloom_level')
    if not bloom_level or not validate_bloom_level(bloom_level):
        return jsonify({'error': 'Invalid Bloom level'}), 400
    
    file = request.files['pdf_file']
    if not file.filename.endswith('.pdf'):
        return jsonify({'error': 'File must be a PDF'}), 400
    
    try:
        file_content = file.read()
        pdf_file = BytesIO(file_content)
        reader = PdfReader(pdf_file)
        
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        controller = get_controller(cohere_key)
        results = controller.process_text_batch(text, bloom_level, max_chars=4000)
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@uploader_bp.route('/bloom-rag/mcq', methods=['POST'])
@login_required
def bloom_rag_mcq_generate():
    """
    MCQ Generator route for Bloom RAG.
    Generates MCQs from uploaded PDF using the same Bloom level and content.
    This is a SEPARATE flow from descriptive question generation.
    """
    cohere_key = _get_cohere_key()
    if not cohere_key:
        flash("COHERE_API_KEY is not configured. Please set it in your .env file.", "danger")
        return redirect(url_for('uploader.bloom_rag_upload'))
    
    subject_id = request.form.get('subject_id')
    bloom_level = request.form.get('bloom_level')
    
    if not subject_id:
        flash("Please select a subject.", "danger")
        return redirect(url_for('uploader.bloom_rag_upload'))
    
    if not bloom_level or not validate_bloom_level(bloom_level):
        flash("Please select a valid Bloom's Taxonomy level.", "danger")
        return redirect(url_for('uploader.bloom_rag_upload'))
    
    if 'pdf_file' not in request.files:
        flash("No file part in the request.", "danger")
        return redirect(url_for('uploader.bloom_rag_upload'))
    
    file = request.files['pdf_file']
    if file.filename == '':
        flash("No file selected.", "danger")
        return redirect(url_for('uploader.bloom_rag_upload'))
    
    if not file.filename.endswith('.pdf'):
        flash("Please upload a PDF file.", "danger")
        return redirect(url_for('uploader.bloom_rag_upload'))
    
    try:
        # Extract text from PDF
        file_content = file.read()
        pdf_file = BytesIO(file_content)
        reader = PdfReader(pdf_file)
        
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        if len(text.strip()) < 50:
            flash("PDF contains very little text. Please ensure the PDF has sufficient content.", "warning")
            return redirect(url_for('uploader.bloom_rag_upload'))
        
        # Initialize Bloom RAG Controller
        controller = get_controller(cohere_key)
        
        # Chunk text
        chunks = controller.chunk_text(text, max_chars=4000)
        current_app.logger.info(f"MCQ Generator: Splitting text into {len(chunks)} chunks.")
        
        # Process each chunk and generate MCQs (using staged format)
        generated_mcqs = []
        errors = []
        staging = {}  # Unit-based staging: {1: [q1a, q1b], 2: [q2a, q2b]}
        
        for result in controller.process_mcq_streaming(text, bloom_level, max_chars=4000):
            unit_number = result.chunk_index + 1
            if result.success:
                # Add to staging structure
                if unit_number not in staging:
                    staging[unit_number] = []
                
                question_index = chr(ord('a') + len(staging[unit_number]))
                question_id = f"{unit_number}{question_index}"
                
                mcq_data = {
                    'question_id': question_id,
                    'unit_number': unit_number,
                    'question_index': question_index,
                    'chunk_index': result.chunk_index,
                    'chunk_text': result.chunk_text[:200] + '...' if len(result.chunk_text) > 200 else result.chunk_text,
                    'question': result.question,
                    'options': result.options,
                    'correct_answer': result.correct_answer,
                    'bloom_level': bloom_level
                }
                staging[unit_number].append(mcq_data)
                generated_mcqs.append(mcq_data)
            else:
                errors.append({
                    'chunk_index': result.chunk_index,
                    'error': result.error
                })
                current_app.logger.error(f"Error generating MCQ for chunk {result.chunk_index}: {result.error}")
        
        # Save MCQs to staging collection (separate from descriptive questions)
        staging_collection = db.collection('staging')
        saved_count = 0
        saved_mcqs = []
        
        for mcq in generated_mcqs:
            try:
                doc_ref = staging_collection.add({
                    'subject_id': subject_id,
                    'unit': mcq['unit_number'],
                    'question_id': mcq['question_id'],
                    'sub_a': mcq['question'],
                    'sub_b': '',
                    'bloom_level': BLOOM_LEVELS.index(bloom_level) + 1,
                    'status': 'pending',
                    'created_at': datetime.utcnow(),
                    'generated_by_ai': True,
                    'source': 'bloom_rag_mcq',
                    'is_mcq': True,
                    'options': mcq['options'],
                    'correct_answer': mcq['correct_answer']
                })
                mcq['id'] = doc_ref[1].id
                subject_doc = db.collection('subjects').document(subject_id).get()
                mcq['subject_name'] = subject_doc.to_dict().get('name', 'Unknown') if subject_doc.exists else 'Unknown'
                saved_mcqs.append(mcq)
                saved_count += 1
            except Exception as e:
                current_app.logger.error(f"Failed to save MCQ to Firestore: {e}")
                continue
        
        if saved_count > 0:
            flash(f"Successfully generated {saved_count} MCQs at {bloom_level} level!", "success")
        
        if errors:
            flash(f"Warning: {len(errors)} chunk(s) failed to generate MCQs.", "warning")
        
        # Get subjects for re-render
        subjects_ref = db.collection('subjects').stream()
        subjects = [{'id': s.id, **s.to_dict()} for s in subjects_ref]
        
        return render_template(
            'bloom_rag_upload.html',
            subjects=subjects,
            bloom_levels=BLOOM_LEVELS,
            generated_mcqs=saved_mcqs,
            mcq_staging=staging,
            errors=errors,
            extracted_text=text,
            total_chunks=len(chunks),
            selected_bloom_level=bloom_level,
            is_mcq_mode=True
        )
        
    except Exception as e:
        current_app.logger.error(f"Error during MCQ generation: {e}")
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('uploader.bloom_rag_upload'))
