import os
import uuid
import json
import re
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from pdfminer.high_level import extract_text
from firebase_admin import storage
from firebase_config import get_db
from .admin import login_required
from blockchain import Blockchain

from routes.bloom_rag_controller import (
    get_controller,
    BLOOM_LEVELS
)

questions_bp = Blueprint('questions', __name__, template_folder='../templates')
db = get_db()

def _get_cohere_key():
    """Get Cohere API key from environment."""
    return os.getenv("COHERE_API_KEY")

def _generate_pdf_questions_with_cohere(unit_number: str, text: str, n: int = 5):
    """Use Cohere via Bloom RAG to generate questions for PDF flow."""
    cohere_key = _get_cohere_key()
    if not cohere_key:
        return []
    
    try:
        controller = get_controller(cohere_key)
        chunks = controller.chunk_text(text, max_chars=4000)
        
        questions = []
        bloom_levels = ["Remember", "Understand", "Apply", "Analyze", "Evaluate"]
        
        for i, chunk in enumerate(chunks[:n]):
            bloom_level = bloom_levels[i % len(bloom_levels)]
            try:
                question = controller.generate_question_for_chunk(chunk, bloom_level)
                questions.append({
                    "question": question,
                    "bloom_level": f"L{BLOOM_LEVELS.index(bloom_level) + 1}",
                    "unit": int(unit_number)
                })
            except Exception as e:
                print(f"Error generating question for chunk {i}: {e}")
                continue
        
        return questions
    except Exception as e:
        print(f"Cohere generation error: {e}")
        return []

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Question Generation Routes ---

@questions_bp.route('/upload-notes', methods=['GET', 'POST'])
@login_required
def upload_notes():
    """Handles PDF note uploads and triggers question generation using Cohere."""
    if request.method == 'POST':
        if 'notes_file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        file = request.files['notes_file']
        subject_id = request.form.get('subject_id')
        unit_number = request.form.get('unit_number')

        if file.filename == '' or not subject_id or not unit_number:
            flash('Missing file, subject, or unit number.', 'danger')
            return redirect(request.url)

        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            try:
                # Extract text from PDF
                extracted_text = extract_text(filepath)
                if len(extracted_text) < 100:
                     flash('PDF content is too short to generate questions.', 'warning')
                     return redirect(url_for('questions.upload_notes'))

                # Generate questions using Cohere
                cohere_key = _get_cohere_key()
                if not cohere_key:
                    flash('COHERE_API_KEY is not configured. Please set it in your .env file.', 'danger')
                    return redirect(url_for('questions.upload_notes'))
                
                generated_questions = _generate_pdf_questions_with_cohere(unit_number, extracted_text, n=5)
                
                if not generated_questions:
                    flash('No questions could be generated from the PDF. Please try with a different document.', 'warning')
                    return redirect(url_for('questions.upload_notes'))

                # Save to staging collection in Firestore
                staging_ref = db.collection('staging')
                for q in generated_questions:
                    q_id = str(uuid.uuid4())
                    q_data = {
                        "question": q.get("question"),
                        "bloom_level": q.get("bloom_level"),
                        "unit": int(q.get("unit", unit_number)),
                        "subject_id": subject_id,
                        "status": "pending"
                    }
                    staging_ref.document(q_id).set(q_data)

                flash(f'{len(generated_questions)} questions generated using Cohere and are pending review.', 'success')

            except json.JSONDecodeError:
                 flash('Failed to parse response from AI. Please try again.', 'danger')
            except Exception as e:
                flash(f'An error occurred: {e}', 'danger')
            finally:
                # Clean up local file
                if os.path.exists(filepath):
                    os.remove(filepath)
            
            return redirect(url_for('questions.staging'))

    # For GET request, fetch subjects to populate the dropdown
    subjects_list = [doc.to_dict() | {'id': doc.id} for doc in db.collection('subjects').stream()]
    return render_template('upload_notes.html', subjects=subjects_list)


# --- Staging Area Routes ---

@questions_bp.route('/staging')
@login_required
def staging():
    """Displays all questions pending review."""
    staging_ref = db.collection('staging')
    questions_list = []
    for doc in staging_ref.stream():
        q_data = doc.to_dict()
        q_data['id'] = doc.id
        
        # Fetch subject name for display (handle missing subject_id)
        subject_id = q_data.get('subject_id')
        if subject_id:
            try:
                subject_doc = db.collection('subjects').document(subject_id).get()
                if subject_doc.exists:
                    q_data['subject_name'] = subject_doc.to_dict().get('name', 'N/A')
                else:
                    q_data['subject_name'] = 'N/A'
            except Exception:
                q_data['subject_name'] = 'N/A'
        else:
            q_data['subject_name'] = 'N/A'
        
        # Ensure required fields have defaults
        q_data.setdefault('bloom_level', 1)
        q_data.setdefault('unit', 1)
        q_data.setdefault('is_mcq', False)
        q_data.setdefault('sub_a', q_data.get('question', ''))
        q_data.setdefault('sub_b', '')
        
        questions_list.append(q_data)
        
    return render_template('staging.html', questions=questions_list)


@questions_bp.route('/staging/action/<question_id>', methods=['POST'])
@login_required
def handle_staging_action(question_id):
    """Handle add/remove actions for staging questions."""
    action = request.form.get('action')
    sub_a = request.form.get('sub_a')
    sub_b = request.form.get('sub_b')
    bloom_level = request.form.get('bloom_level')
    unit = request.form.get('unit')

    try:
        staging_ref = db.collection('staging').document(question_id)
        question_doc = staging_ref.get()

        if not question_doc.exists:
            flash('Question not found in staging.', 'danger')
            return redirect(url_for('questions.staging'))

        question_data = question_doc.to_dict()

        if action == 'add':
            # Transfer to syllabus collection for question paper generation
            syllabus_data = {
                'subject_id': question_data['subject_id'],
                'unit': int(unit) if unit else question_data.get('unit', 1),
                'sub_a': sub_a.strip() if sub_a else question_data.get('sub_a', ''),
                'sub_b': sub_b.strip() if sub_b else question_data.get('sub_b', ''),
                'bloom_level': int(bloom_level.replace('L', '')) if bloom_level else question_data.get('bloom_level', 1),
                'status': 'approved',
                'generated_by_ai': True,
                'added_from_staging': True,
                'created_at': question_data.get('created_at', datetime.utcnow())
            }

            # Add to questions collection
            questions_ref = db.collection('questions')
            new_question_id = str(uuid.uuid4())
            questions_ref.document(new_question_id).set(syllabus_data)

            # Remove from staging
            staging_ref.delete()

            # Add to blockchain for verification
            blockchain = Blockchain()
            blockchain.new_transaction(
                question_id=new_question_id,
                question_text=f"{syllabus_data['sub_a']} {syllabus_data['sub_b']}",
                bloom_level=f"L{syllabus_data['bloom_level']}"
            )

            flash('Question added to syllabus collection for question paper generation.', 'success')

        elif action == 'remove':
            # Delete from staging
            staging_ref.delete()
            flash('Question removed from staging.', 'info')

        else:
            flash('Invalid action.', 'danger')

    except Exception as e:
        flash(f'An error occurred: {e}', 'danger')

    return redirect(url_for('questions.staging'))


# --- Syllabus-based Generation Routes ---

@questions_bp.route('/syllabus-generator', methods=['GET', 'POST'])
@login_required
def syllabus_generator():
    """Generate questions from syllabus text input using Cohere."""
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        unit_number = request.form.get('unit_number')
        num_pairs = int(request.form.get('num_pairs', 5))
        syllabus_text = request.form.get('syllabus_text', '').strip()

        if not subject_id or not unit_number or not syllabus_text:
            flash('Subject, unit number, and syllabus text are required.', 'danger')
            return redirect(request.url)

        try:
            # Use Cohere via Bloom RAG Controller for question generation
            cohere_key = _get_cohere_key()
            if not cohere_key:
                flash("COHERE_API_KEY is not configured. Please set it in your .env file.", "danger")
                return redirect(request.url)

            controller = get_controller(cohere_key)
            chunks = controller.chunk_text(syllabus_text, max_chars=4000)
            
            # Generate questions for each chunk
            generated_questions = []
            bloom_levels = ["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"]
            
            for i, chunk in enumerate(chunks[:num_pairs]):
                bloom_level = bloom_levels[i % len(bloom_levels)]
                try:
                    question_a = controller.generate_question_for_chunk(chunk, bloom_level)
                    # Generate a second question at a different level
                    next_level = bloom_levels[(i + 1) % len(bloom_levels)]
                    question_b = controller.generate_question_for_chunk(chunk, next_level)
                    
                    generated_questions.append({
                        'unit': int(unit_number),
                        'question_text_a': question_a,
                        'question_text_b': question_b,
                        'bloom_level': BLOOM_LEVELS.index(bloom_level) + 1
                    })
                except Exception as e:
                    print(f"Error generating question for chunk {i}: {e}")
                    continue

            # Save questions to staging area
            count = 0
            staging_ref = db.collection('staging')
            for q_data in generated_questions:
                try:
                    staging_ref.add({
                        'subject_id': subject_id,
                        'unit': q_data['unit'],
                        'sub_a': q_data['question_text_a'].strip(),
                        'sub_b': q_data['question_text_b'].strip(),
                        'bloom_level': q_data['bloom_level'],
                        'status': 'pending',
                        'created_at': datetime.utcnow(),
                        'generated_by_ai': True,
                        'source': 'syllabus_text'
                    })
                    count += 1
                except Exception as e:
                    print(f"Error saving question: {e}")
                    continue

            if count == 0:
                flash("No valid questions could be generated from the syllabus text.", "warning")
            else:
                flash(f"Successfully generated {count} questions using Cohere and added them to staging for review!", "success")

        except Exception as e:
            flash(f"An error occurred: {e}", "danger")

        return redirect(url_for('questions.staging'))

    # For GET request
    subjects_ref = db.collection('subjects').stream()
    subjects = [{'id': s.id, **s.to_dict()} for s in subjects_ref]
    return render_template('syllabus_generator.html', subjects=subjects)


# ============================================================
# Custom Questions
# ============================================================

@questions_bp.route('/custom', methods=['GET', 'POST'])
@login_required
def custom_question():
    """Allow admin to manually add a custom question to the bank."""
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        unit_number = request.form.get('unit_number')
        question_text = request.form.get('question_text')
        bloom_level = request.form.get('bloom_level', 'L1')
        hardness = request.form.get('hardness', 'medium')

        if not subject_id or not unit_number or not question_text:
            flash("Subject, unit, and question text are required.", "danger")
            return redirect(url_for('questions.custom_question'))

        try:
            q_id = str(uuid.uuid4())
            data = {
                "subject_id": subject_id,
                "unit": int(unit_number),
                "question": question_text,
                "bloom_level": bloom_level,
                "hardness": hardness,
                "status": "approved",
                "is_custom": True
            }
            db.collection("questions").document(q_id).set(data)

            # Append to blockchain
            blockchain = Blockchain()
            blockchain.new_transaction(
                question_id=q_id,
                question_text=question_text,
                bloom_level=bloom_level
            )

            flash("Custom question added successfully and secured in blockchain.", "success")
        except Exception as e:
            flash(f"Failed to add custom question: {e}", "danger")

        return redirect(url_for('questions.custom_question'))

    subjects_list = [doc.to_dict() | {'id': doc.id} for doc in db.collection('subjects').stream()]
    return render_template("custom_questions.html", subjects=subjects_list)


# ============================================================
# Syllabus Questions Management
# ============================================================

@questions_bp.route('/syllabus-questions')
@login_required
def syllabus_questions():
    """Display all syllabus-based generated questions for management."""
    questions_ref = db.collection('questions')
    syllabus_questions = []

    # Filter for questions added from staging (syllabus-based)
    for doc in questions_ref.where('added_from_staging', '==', True).stream():
        q_data = doc.to_dict()
        q_data['id'] = doc.id

        # Fetch subject name for display
        subject_doc = db.collection('subjects').document(q_data['subject_id']).get()
        if subject_doc.exists:
            q_data['subject_name'] = subject_doc.to_dict().get('name', 'N/A')

        syllabus_questions.append(q_data)

    return render_template('syllabus_questions.html', questions=syllabus_questions)


# ============================================================
# Online MCQ Generator
# ============================================================

@questions_bp.route('/mcq-generator', methods=['GET', 'POST'])
@login_required
def mcq_generator():
    """Generate MCQs automatically from text using Cohere."""
    mcqs = []
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        unit_number = request.form.get('unit_number')
        input_text = request.form.get('input_text', '').strip()

        if not subject_id or not unit_number or not input_text:
            flash("Subject, unit, and some input text are required.", "danger")
            return redirect(url_for('questions.mcq_generator'))

        try:
            cohere_key = _get_cohere_key()
            if not cohere_key:
                flash("COHERE_API_KEY is not configured. Please set it in your .env file.", "danger")
                return redirect(url_for('questions.mcq_generator'))
            
            controller = get_controller(cohere_key)
            chunks = controller.chunk_text(input_text, max_chars=2000)
            
            # Generate MCQ-style questions using Cohere
            bloom_levels = ["Remember", "Understand", "Apply"]
            
            for i, chunk in enumerate(chunks[:5]):
                bloom_level = bloom_levels[i % len(bloom_levels)]
                try:
                    question = controller.generate_question_for_chunk(chunk, bloom_level)
                    mcqs.append({
                        "question": question,
                        "options": ["Option A", "Option B", "Option C", "Option D"],
                        "answer": "Option A",
                        "note": "Please review and update options/answer manually."
                    })
                except Exception as e:
                    print(f"Error generating MCQ for chunk {i}: {e}")
                    continue

            if mcqs:
                flash(f"{len(mcqs)} MCQ questions generated using Cohere. Please update options and answers manually.", "success")
            else:
                flash("No MCQs could be generated. Please try with different content.", "warning")
                
        except Exception as e:
            flash(f"MCQ generation failed: {e}", "danger")

    subjects_list = [doc.to_dict() | {'id': doc.id} for doc in db.collection('subjects').stream()]
    return render_template("mcq_generator.html", subjects=subjects_list, mcqs=mcqs)

# ============================================================
# Final Questions
# ============================================================

@questions_bp.route('/final-questions')
@login_required
def final_questions():
    """Display all approved questions, grouped by subject."""
    questions_ref = db.collection('questions')
    subjects_ref = db.collection('subjects')

    subjects = {doc.id: doc.to_dict() for doc in subjects_ref.stream()}
    
    questions_by_subject = {}
    for question_doc in questions_ref.where('status', '==', 'approved').stream():
        question = question_doc.to_dict()
        subject_id = question.get('subject_id')
        if subject_id in subjects:
            if subject_id not in questions_by_subject:
                questions_by_subject[subject_id] = {
                    'name': subjects[subject_id].get('name', 'Unknown Subject'),
                    'questions': []
                }
            questions_by_subject[subject_id]['questions'].append(question)

    return render_template('final_questions.html', questions_by_subject=questions_by_subject)
