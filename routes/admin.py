from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from firebase_config import log_activity
from firebase_admin import auth
from functools import wraps
from blockchain import Blockchain
from firebase_config import get_db
from firebase_config import get_bucket
from datetime import datetime
import uuid
import os

admin_bp = Blueprint('admin', __name__, template_folder='../templates')

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

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handles admin login. GET shows the page, POST verifies the token."""
    # This block handles the POST request from the JavaScript fetch.
    if request.method == 'POST':
        try:
            # Get the ID token from the JSON body sent by the fetch request
            id_token = request.json.get('idToken')
            if not id_token:
                return jsonify({"status": "error", "message": "ID token is missing."}), 400

            # Verify the ID token. Allow clock skew if local clock is slightly behind.
            # Maximum allowed is 60 seconds (Firebase Admin SDK limit)
            try:
                decoded_token = auth.verify_id_token(id_token, clock_skew_seconds=60)
            except TypeError:
                # Older firebase_admin versions may not support clock_skew_seconds
                decoded_token = auth.verify_id_token(id_token)
            
            # Store user info in the server-side session
            session['user'] = decoded_token['uid']
            session['email'] = decoded_token.get('email', 'No email')
            session.permanent = True

            # Send a success response back to the JavaScript
            try:
                log_activity(session['user'], 'login', {'email': session['email']})
            except Exception:
                pass
            return jsonify({"status": "success"}), 200

        except Exception as e:
            # If verification fails, send a JSON error back to the JavaScript
            return jsonify({"status": "error", "message": f"Login failed: {e}"}), 401
    
    # This block handles the GET request when you first visit the page.
    # If a user is already logged in, it sends them to the dashboard.
    if 'user' in session:
        return redirect(url_for('admin.dashboard'))
        
    # Otherwise, it just shows the login page.
    return render_template('login.html')

@admin_bp.route('/logout')
@login_required
def logout():
    """Logs the current user out."""
    try:
        if 'user' in session:
            log_activity(session['user'], 'logout', {'email': session.get('email')})
    except Exception:
        pass
    session.pop('user', None)
    session.pop('email', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin.login'))

@admin_bp.route('/dashboard')
def dashboard():
    # compute initial total_subjects for first render
    total_subjects = 0
    try:
        # Use Firestore client from firebase_config
        db = get_db()
        # count documents in 'subjects' collection
        total_subjects = sum(1 for _ in db.collection('subjects').stream())
    except Exception as e:
        # final fallback: 0 (or log)
        current_app.logger.debug(f'Could not determine subject count automatically: {e}')
        total_subjects = 0

    return render_template('dashboard.html', total_subjects=total_subjects)

# JSON endpoint used by dashboard JS to refresh count
@admin_bp.route('/subjects/count')
def subject_count():
    total = 0
    try:
        db = get_db()
        total = sum(1 for _ in db.collection('subjects').stream())
    except Exception as e:
        current_app.logger.debug(f'subject_count: fallback to 0, error: {e}')
        total = 0
    return jsonify({'count': total})

@admin_bp.route('/verify-blockchain')
@login_required
def verify_blockchain():
    """Verifies the integrity of the blockchain."""
    is_valid = Blockchain().is_chain_valid()
    if is_valid:
        flash('Blockchain integrity verified. The chain is valid.', 'success')
    else:
        flash('Blockchain integrity check failed! The chain has been tampered with.', 'danger')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/logs')
@login_required
def activity_logs():
    """Displays recent activity logs from Firestore."""
    try:
        db = get_db()
        # Timestamps are stored as ISO strings, so order descending lexicographically works
        logs = [doc.to_dict() | {'id': doc.id} for doc in db.collection('activity_logs').order_by('timestamp', direction='DESCENDING').limit(200).stream()]
    except Exception:
        logs = []
        flash('Could not load activity logs.', 'warning')
    return render_template('activity_logs.html', logs=logs)

@admin_bp.route('/upload-paper', methods=['GET', 'POST'])
@login_required
def upload_paper():
    db = get_db()
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
                    storage_key = f"sample_papers/{file.filename}_{uuid.uuid4()}"
                    blob = bucket.blob(storage_key)
                    file.seek(0)
                    blob.upload_from_file(file)
                    blob.make_public()
                    download_url = blob.public_url

                db.collection('question_papers').add({
                    'subject_name': subject_name,
                    'exam_session': 'Sample Paper',
                    'download_url': download_url,
                    'created_at': datetime.utcnow()
                })

                flash("Sample paper uploaded successfully!", "success")
                return redirect(url_for('admin.dashboard'))

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

@admin_bp.route('/generated-pdfs')
@login_required
def generated_pdfs():
    try:
        db = get_db()
        generated_ref = db.collection('generated_papers').stream()
        generated_by_subject = {}
        for gen_doc in generated_ref:
            gen = gen_doc.to_dict()
            gen_subject = gen.get('subject_name', 'Unknown Subject')
            if gen_subject not in generated_by_subject:
                generated_by_subject[gen_subject] = []
            generated_by_subject[gen_subject].append(gen)
    except Exception as e:
        flash(f'Error fetching generated papers: {e}', 'danger')
        generated_by_subject = {}
    return render_template('student_papers.html', papers_by_subject={}, generated_by_subject=generated_by_subject, subjects=[])