from flask import Blueprint, render_template, request, redirect, url_for, flash
from firebase_config import get_db, log_activity
from .admin import login_required
import uuid
import os

management_bp = Blueprint('management', __name__, template_folder='../templates')
db = get_db()

# --- Branch Management Routes ---

@management_bp.route('/branches', methods=['GET', 'POST'])
@login_required
def branches():
    """Handles listing and adding new academic branches."""
    branches_ref = db.collection('branches')
    
    if request.method == 'POST':
        branch_name = request.form.get('branch_name')
        if branch_name:
            # Generate a unique ID for the new branch
            branch_id = str(uuid.uuid4())
            branches_ref.document(branch_id).set({'name': branch_name})
            flash(f"Branch '{branch_name}' added successfully.", 'success')
            try:
                from flask import session as _session
                log_activity(_session.get('user', 'anonymous'), 'branch_add', {
                    'branch_id': branch_id,
                    'branch_name': branch_name
                })
            except Exception:
                pass
        else:
            flash('Branch name cannot be empty.', 'danger')
        return redirect(url_for('management.branches'))

    # Fetch all branches for GET request
    branches_list = [doc.to_dict() | {'id': doc.id} for doc in branches_ref.stream()]
    return render_template('branches.html', branches=branches_list)

@management_bp.route('/branches/delete/<branch_id>', methods=['POST'])
@login_required
def delete_branch(branch_id):
    """Handles deleting an academic branch."""
    try:
        db.collection('branches').document(branch_id).delete()
        flash('Branch deleted successfully.', 'success')
        try:
            from flask import session as _session
            log_activity(_session.get('user', 'anonymous'), 'branch_delete', {'branch_id': branch_id})
        except Exception:
            pass
    except Exception as e:
        flash(f'Error deleting branch: {e}', 'danger')
    return redirect(url_for('management.branches'))

# --- Subject Management Routes ---

@management_bp.route('/subjects', methods=['GET', 'POST'])
@login_required
def subjects():
    """Handles listing and adding new subjects, linking them to a branch."""
    subjects_ref = db.collection('subjects')
    branches_ref = db.collection('branches')

    if request.method == 'POST':
        subject_name = request.form.get('subject_name')
        branch_id = request.form.get('branch_id')
        curriculum = request.form.get('curriculum')
        
        if subject_name and branch_id and curriculum:
            # Get branch name for storage to make retrieval easier
            branch_doc = branches_ref.document(branch_id).get()
            if branch_doc.exists:
                branch_name = branch_doc.to_dict().get('name')
                subject_id = str(uuid.uuid4())
                subjects_ref.document(subject_id).set({
                    'name': subject_name,
                    'branch_id': branch_id,
                    'branch_name': branch_name,
                    'curriculum': curriculum
                })

                # Ensure folder structure uploads/subjects/<branch>/<subject>
                def sanitize_name(name: str) -> str:
                    safe = name.strip().replace(' ', '_')
                    # Remove characters not allowed in Windows file names <>:"/\|?*
                    return ''.join(ch for ch in safe if ch not in '<>:"/\\|?*')

                base_uploads = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'uploads', 'subjects')
                branch_folder = sanitize_name(branch_name or 'unknown_branch')
                curriculum_folder = sanitize_name(curriculum)
                subject_folder = sanitize_name(subject_name)
                abs_path = os.path.abspath(os.path.join(base_uploads, branch_folder, curriculum_folder, subject_folder))
                try:
                    os.makedirs(abs_path, exist_ok=True)
                except Exception as e:
                    # Non-fatal: inform user but continue
                    flash(f"Created subject but could not create folder: {e}", 'warning')

                flash(f"Subject '{subject_name}' added successfully.", 'success')
                try:
                    from flask import session as _session
                    log_activity(_session.get('user', 'anonymous'), 'subject_add', {
                        'subject_id': subject_id,
                        'subject_name': subject_name,
                        'branch_id': branch_id,
                        'branch_name': branch_name,
                        'curriculum': curriculum
                    })
                except Exception:
                    pass
            else:
                flash('Selected branch does not exist.', 'danger')
        else:
            flash('Subject name, branch and regulation are required.', 'danger')
        return redirect(url_for('management.subjects'))

    # Fetch all subjects and branches for GET request
    subjects_list = [doc.to_dict() | {'id': doc.id} for doc in subjects_ref.stream()]
    branches_list = [doc.to_dict() | {'id': doc.id} for doc in branches_ref.stream()]

    # Group subjects by branch id for easier rendering
    grouped_by_branch = {}
    for subject in subjects_list:
        b_id = subject.get('branch_id')
        grouped_by_branch.setdefault(b_id, []).append(subject)

    # Map of branch id to name for template convenience
    branch_id_to_name = {b['id']: b.get('name') for b in branches_list}
    
    return render_template(
        'subjects.html',
        subjects=subjects_list,
        branches=branches_list,
        grouped_subjects=grouped_by_branch,
        branch_id_to_name=branch_id_to_name
    )

@management_bp.route('/subjects/delete/<subject_id>', methods=['POST'])
@login_required
def delete_subject(subject_id):
    """Handles deleting a subject."""
    try:
        db.collection('subjects').document(subject_id).delete()
        flash('Subject deleted successfully.', 'success')
        try:
            from flask import session as _session
            log_activity(_session.get('user', 'anonymous'), 'subject_delete', {'subject_id': subject_id})
        except Exception:
            pass
    except Exception as e:
        flash(f'Error deleting subject: {e}', 'danger')
    return redirect(url_for('management.subjects'))

