from flask import Blueprint, render_template, flash, request, redirect, url_for, current_app, send_from_directory
from firebase_config import get_db, get_bucket
from datetime import datetime
import uuid
import os

student_bp = Blueprint('student', __name__, template_folder='../templates')
db = get_db()

@student_bp.route('/papers')
def papers():
    """Displays all available question papers for students."""
    try:
        papers_ref = db.collection('question_papers').stream()
        papers_by_subject = {}
        for paper_doc in papers_ref:
            paper = paper_doc.to_dict()
            subject_name = paper.get('subject_name', 'Unknown Subject')
            if subject_name not in papers_by_subject:
                papers_by_subject[subject_name] = []
            papers_by_subject[subject_name].append(paper)
        generated_ref = db.collection('generated_papers').stream()
        generated_by_subject = {}
        for gen_doc in generated_ref:
            gen = gen_doc.to_dict()
            gen_subject = gen.get('subject_name', 'Unknown Subject')
            if gen_subject not in generated_by_subject:
                generated_by_subject[gen_subject] = []
            generated_by_subject[gen_subject].append(gen)
    except Exception as e:
        flash(f'Error fetching question papers: {e}', 'danger')
        papers_by_subject = {}
        generated_by_subject = {}
    
    subjects_ref = db.collection('subjects').stream()
    subjects = [{'id': s.id, **s.to_dict()} for s in subjects_ref]
        
    return render_template('student_papers.html', papers_by_subject=papers_by_subject, generated_by_subject=generated_by_subject, subjects=subjects)

@student_bp.route('/upload-paper', methods=['GET', 'POST'])
def upload_paper():
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        if not subject_id:
            flash("Please select a subject.", "danger")
            return redirect(request.url)
        
        subject_doc = db.collection('subjects').document(subject_id).get()
        if not subject_doc.exists:
            flash("Selected subject not found.", "danger")
            return redirect(request.url)
        subject_name = subject_doc.to_dict().get('name', 'Unknown Subject')

        if 'paper_file' not in request.files:
            flash("No file part in the request.", "danger")
            return redirect(request.url)

        file = request.files['paper_file']
        if file.filename == '':
            flash("No file selected.", "danger")
            return redirect(request.url)

        if file and file.filename.endswith('.pdf'):
            try:
                use_local = os.getenv("USE_LOCAL_STORAGE", "1") == "1"
                if use_local:
                    base_dir = os.getenv("PREVIOUS_QUE_DIR", os.path.join(current_app.root_path, 'PREVIOUS_Que'))
                    os.makedirs(base_dir, exist_ok=True)
                    unique_name = f"{uuid.uuid4()}_{os.path.basename(file.filename)}"
                    local_path = os.path.join(base_dir, unique_name)
                    file.seek(0)
                    file.save(local_path)
                    download_url = url_for('student.download_previous', filename=unique_name)
                else:
                    bucket = get_bucket()
                    if not bucket:
                        flash("Cloud Storage is not configured. Set FIREBASE_STORAGE_BUCKET in .env.", "danger")
                        return redirect(request.url)
                    pdf_path = f"sample_papers/{file.filename}_{uuid.uuid4()}"
                    blob = bucket.blob(pdf_path)
                    file.seek(0)
                    blob.upload_from_file(file)
                    blob.make_public()
                    download_url = blob.public_url

                # Save metadata to Firestore
                db.collection('question_papers').add({
                    'subject_name': subject_name,
                    'exam_session': 'Sample Paper',
                    'download_url': download_url,
                    'created_at': datetime.utcnow()
                })

                flash("Sample paper uploaded successfully!", "success")
                return redirect(url_for('student.papers'))

            except Exception as e:
                err_msg = str(e)
                if "The specified bucket does not exist" in err_msg or "notFound" in err_msg:
                    flash("Upload failed: Storage bucket not found. Check FIREBASE_STORAGE_BUCKET and Firebase Storage setup.", "danger")
                else:
                    flash(f"An error occurred: {e}", "danger")
                return redirect(request.url)

    subjects_ref = db.collection('subjects').stream()
    subjects = [{'id': s.id, **s.to_dict()} for s in subjects_ref]
    return render_template('upload_paper.html', subjects=subjects)

@student_bp.route('/download/<path:filename>')
def download_previous(filename):
    base_dir = os.getenv("PREVIOUS_QUE_DIR", os.path.join(current_app.root_path, 'PREVIOUS_Que'))
    return send_from_directory(base_dir, filename, as_attachment=False)
