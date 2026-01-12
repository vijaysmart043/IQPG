import os
import random
from flask import Blueprint, request, render_template, send_file, current_app, session, redirect, url_for, flash
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Frame, PageTemplate
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import inch
from firebase_config import db, get_bucket
from datetime import datetime
from functools import wraps
import uuid

generator_bp = Blueprint('generator', __name__)

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

# --- ReportLab Header Function ---
def header(canvas, doc):
    canvas.saveState()
    styles = getSampleStyleSheet()
    
    # University Header
    header_text = "SRK INSTITUTE OF TECHNOLOGY"
    p_header = Paragraph(header_text, styles['Title'])
    w_header, h_header = p_header.wrap(doc.width, doc.topMargin)
    p_header.drawOn(canvas, doc.leftMargin, doc.height + 0.75 * inch)

    # Sub-header
    sub_header_text = "(An Autonomous Institution – UGC, Govt. of India)"
    p_sub_header = Paragraph(sub_header_text, styles['Normal'])
    w_sub, h_sub = p_sub_header.wrap(doc.width, doc.topMargin)
    p_sub_header.drawOn(canvas, doc.leftMargin, doc.height + 0.5 * inch)
    
    canvas.restoreState()

# --- ROUTES ---

@generator_bp.route('/generate', methods=['GET', 'POST'])
@login_required
def generate_paper():
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        exam_session = request.form.get('exam_session', os.getenv('EXAM_SESSION', 'Fall 2024'))
        
        if not subject_id:
            return "Subject ID is required.", 400
        
        return generate_paper_pdf(subject_id, exam_session)

    subjects_ref = db.collection('subjects').stream()
    subjects = []
    for s in subjects_ref:
        data = s.to_dict()
        data['id'] = s.id
        subjects.append(data)
    exam_session = os.getenv('EXAM_SESSION', 'Fall 2024')
    return render_template('generate_paper.html', subjects=subjects, exam_session=exam_session)

def generate_paper_pdf(subject_id, exam_session):
    try:
        # Fetch subject details
        subject_doc = db.collection('subjects').document(subject_id).get()
        if not subject_doc.exists:
            return "Subject not found.", 404
        subject = subject_doc.to_dict()

        # Fetch all approved questions for the subject
        questions_ref = db.collection('questions').where('subject_id', '==', subject_id).stream()
        
        all_questions = []
        for q_doc in questions_ref:
            q_data = q_doc.to_dict()
            q_data['id'] = q_doc.id
            all_questions.append(q_data)

        # Group questions by Bloom's level
        level_questions = {2: [], 3: [], 4: []}
        for q in all_questions:
            level = q.get('level', 3)
            if level in level_questions:
                level_questions[level].append(q)

        # Select questions per blueprint: up to 7 L2, 2 L3, 1 L4 (take available if less)
        selected_questions = []
        selected_questions.extend(random.sample(level_questions[2], min(7, len(level_questions[2]))))
        selected_questions.extend(random.sample(level_questions[3], min(2, len(level_questions[3]))))
        selected_questions.extend(random.sample(level_questions[4], min(1, len(level_questions[4]))))

        # Check if we have at least 1 question
        if len(selected_questions) < 1:
            return "No questions available for this subject.", 400

        # Assign up to 2 questions per unit from selected
        paper_content = {}
        for unit in range(1, 6):
            unit_candidates = [q for q in selected_questions if q.get('unit') == unit]
            num_to_take = min(2, len(unit_candidates))
            paper_content[unit] = random.sample(unit_candidates, num_to_take) if num_to_take > 0 else []
            
        # --- PDF Generation using ReportLab ---
        use_local = os.getenv("USE_LOCAL_STORAGE", "1") == "1"
        if use_local:
            base_dir = os.getenv("PREVIOUS_QUE_DIR", os.path.join(current_app.root_path, 'PREVIOUS_Que'))
            os.makedirs(base_dir, exist_ok=True)
            unique_name = f"{subject_id}_{uuid.uuid4()}.pdf"
            pdf_path = os.path.join(base_dir, unique_name)
        else:
            pdf_path = f"question_paper_{subject_id}_{uuid.uuid4()}.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=1.5*inch, bottomMargin=inch)
        
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='Center', alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='Question', parent=styles['Normal'], leftIndent=20))
        styles.add(ParagraphStyle(name='SubQuestion', parent=styles['Normal'], leftIndent=40))

        story = []
        
        # Title and Info
        story.append(Paragraph(f"B.Tech II Year I Semester Examinations, {exam_session}", styles['Center']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(subject.get('name', 'Subject Name'), styles['Center']))
        story.append(Spacer(1, 24))
        
        # Instructions
        story.append(Paragraph("Time: 3 hours", styles['Normal']))
        story.append(Paragraph("Max. Marks: 70", styles['Normal']))
        story.append(Spacer(1, 24))

        for unit_num, questions in paper_content.items():
            if not questions:
                continue
            story.append(Paragraph(f"<b>UNIT - {unit_num}</b>", styles['Normal']))
            story.append(Spacer(1, 12))

            for i, q in enumerate(questions):
                question_num = 2*unit_num - 1 + i
                story.append(Paragraph(f"<b>{question_num}.</b>", styles['Question']))
                story.append(Paragraph(f"a) {q['sub_a']}", styles['SubQuestion']))
                story.append(Spacer(1, 6))
                story.append(Paragraph(f"b) {q['sub_b']}", styles['SubQuestion']))
                if i < len(questions) - 1:
                    story.append(Spacer(1, 12))
                    story.append(Paragraph("<b>OR</b>", styles['Center']))
                    story.append(Spacer(1, 12))
                else:
                    story.append(Spacer(1, 24))
        
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height - doc.topMargin, id='normal')
        template = PageTemplate(id='main_template', frames=[frame], onPage=header)
        doc.addPageTemplates([template])
        
        doc.build(story)

        try:
            if use_local:
                filename = os.path.basename(pdf_path)
                download_url = url_for('student.download_previous', filename=filename)
                db.collection('generated_papers').add({
                    'subject_id': subject_id,
                    'subject_name': subject.get('name', 'Subject Name'),
                    'exam_session': exam_session,
                    'download_url': download_url,
                    'created_at': datetime.utcnow()
                })
            else:
                bucket = get_bucket()
                if bucket:
                    storage_key = f"generated_papers/{subject_id}_{uuid.uuid4()}.pdf"
                    blob = bucket.blob(storage_key)
                    blob.upload_from_filename(pdf_path)
                    blob.make_public()
                    download_url = blob.public_url
                    db.collection('generated_papers').add({
                        'subject_id': subject_id,
                        'subject_name': subject.get('name', 'Subject Name'),
                        'exam_session': exam_session,
                        'download_url': download_url,
                        'created_at': datetime.utcnow()
                    })
        except Exception:
            pass

        return send_file(pdf_path, as_attachment=True)

    except Exception as e:
        current_app.logger.error(f"Error generating PDF: {e}")
        return f"An error occurred while generating the paper: {e}", 500

@generator_bp.route('/generate-final-paper/<subject_id>')
@login_required
def generate_final_paper_pdf(subject_id):
    try:
        # Fetch subject details
        subject_doc = db.collection('subjects').document(subject_id).get()
        if not subject_doc.exists:
            return "Subject not found.", 404
        subject = subject_doc.to_dict()

        # Fetch all approved questions for the subject
        questions_ref = db.collection('questions').where('subject_id', '==', subject_id).where('status', '==', 'approved').stream()
        
        all_questions = []
        for q_doc in questions_ref:
            q_data = q_doc.to_dict()
            q_data['id'] = q_doc.id
            all_questions.append(q_data)

        # Group questions by Bloom's level
        level_questions = {2: [], 3: [], 4: []}
        for q in all_questions:
            level = q.get('level', 3)
            if level in level_questions:
                level_questions[level].append(q)

        # Select questions per blueprint: up to 7 L2, 2 L3, 1 L4 (take available if less)
        selected_questions = []
        selected_questions.extend(random.sample(level_questions[2], min(7, len(level_questions[2]))))
        selected_questions.extend(random.sample(level_questions[3], min(2, len(level_questions[3]))))
        selected_questions.extend(random.sample(level_questions[4], min(1, len(level_questions[4]))))

        # Check if we have at least 1 question
        if len(selected_questions) < 1:
            return "No questions available for this subject.", 400

        # Assign up to 2 questions per unit from selected
        paper_content = {}
        for unit in range(1, 6):
            unit_candidates = [q for q in selected_questions if q.get('unit') == unit]
            num_to_take = min(2, len(unit_candidates))
            paper_content[unit] = random.sample(unit_candidates, num_to_take) if num_to_take > 0 else []
            
        # --- PDF Generation using ReportLab ---
        use_local = os.getenv("USE_LOCAL_STORAGE", "1") == "1"
        if use_local:
            base_dir = os.getenv("PREVIOUS_QUE_DIR", os.path.join(current_app.root_path, 'PREVIOUS_Que'))
            os.makedirs(base_dir, exist_ok=True)
            unique_name = f"final_{subject_id}_{uuid.uuid4()}.pdf"
            pdf_path = os.path.join(base_dir, unique_name)
        else:
            pdf_path = f"final_question_paper_{subject_id}_{uuid.uuid4()}.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=1.5*inch, bottomMargin=inch)
        
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='Center', alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='Question', parent=styles['Normal'], leftIndent=20))
        styles.add(ParagraphStyle(name='SubQuestion', parent=styles['Normal'], leftIndent=40))

        story = []
        
        # Title and Info
        story.append(Paragraph(f"Final Questions - {subject.get('name', 'Subject Name')}", styles['Center']))
        story.append(Spacer(1, 12))
        story.append(Paragraph("B.Tech II Year I Semester Examinations, Final 2025", styles['Center']))
        story.append(Spacer(1, 24))
        
        # Instructions
        story.append(Paragraph("Time: 3 hours", styles['Normal']))
        story.append(Paragraph("Max. Marks: 70", styles['Normal']))
        story.append(Spacer(1, 24))
        
        for unit_num, questions in paper_content.items():
            if not questions:
                continue
            story.append(Paragraph(f"<b>UNIT - {unit_num}</b>", styles['Normal']))
            story.append(Spacer(1, 12))

            for i, q in enumerate(questions):
                question_num = 2*unit_num - 1 + i
                story.append(Paragraph(f"<b>{question_num}.</b>", styles['Question']))
                story.append(Paragraph(f"a) {q['sub_a']}", styles['SubQuestion']))
                story.append(Spacer(1, 6))
                story.append(Paragraph(f"b) {q['sub_b']}", styles['SubQuestion']))
                if i < len(questions) - 1:
                    story.append(Spacer(1, 12))
                    story.append(Paragraph("<b>OR</b>", styles['Center']))
                    story.append(Spacer(1, 12))
                else:
                    story.append(Spacer(1, 24))
        
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height - doc.topMargin, id='normal')
        template = PageTemplate(id='main_template', frames=[frame], onPage=header)
        doc.addPageTemplates([template])
        
        doc.build(story)

        try:
            if use_local:
                filename = os.path.basename(pdf_path)
                download_url = url_for('student.download_previous', filename=filename)
                db.collection('generated_papers').add({
                    'subject_id': subject_id,
                    'subject_name': subject.get('name', 'Subject Name'),
                    'exam_session': 'Final 2025',
                    'download_url': download_url,
                    'created_at': datetime.utcnow()
                })
            else:
                bucket = get_bucket()
                if bucket:
                    storage_key = f"generated_papers/final_{subject_id}_{uuid.uuid4()}.pdf"
                    blob = bucket.blob(storage_key)
                    blob.upload_from_filename(pdf_path)
                    blob.make_public()
                    download_url = blob.public_url
                    db.collection('generated_papers').add({
                        'subject_id': subject_id,
                        'subject_name': subject.get('name', 'Subject Name'),
                        'exam_session': 'Final 2025',
                        'download_url': download_url,
                        'created_at': datetime.utcnow()
                    })
        except Exception:
            pass

        return send_file(pdf_path, as_attachment=True)

    except Exception as e:
        current_app.logger.error(f"Error generating final PDF: {e}")
        return f"An error occurred while generating the final paper: {e}", 500
