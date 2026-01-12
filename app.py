import os
from flask import Flask
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def create_app():
    """
    Creates and configures a Flask application instance.
    """
    app = Flask(__name__)
    app.secret_key = os.urandom(24)

    # Load configuration from environment variables
    app.config['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
    app.config['FIREBASE_STORAGE_BUCKET'] = os.getenv('FIREBASE_STORAGE_BUCKET')
    app.config['EXAM_SESSION'] = os.getenv('EXAM_SESSION')
    app.config['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    
    # Load Cohere API key for Bloom RAG
    app.config['COHERE_API_KEY'] = os.getenv('COHERE_API_KEY')
    app.config['PINECONE_API_KEY'] = os.getenv('PINECONE_API_KEY')
    app.config['PINECONE_ENVIRONMENT'] = os.getenv('PINECONE_ENVIRONMENT')
    
    # Initialize Firebase, Blockchain, etc. within the app context
    with app.app_context():
        from firebase_config import init_firebase
        from blockchain import Blockchain

        init_firebase()
        Blockchain()

        # Import and register blueprints for different routes
        from routes.admin import admin_bp
        from routes.management import management_bp
        from routes.questions import questions_bp
        from routes.generator import generator_bp
        from routes.mcq import mcq_bp
        from routes.uploader import uploader_bp 
        from routes.student import student_bp

        app.register_blueprint(admin_bp, url_prefix='/admin')
        app.register_blueprint(management_bp, url_prefix='/manage')
        app.register_blueprint(questions_bp, url_prefix='/questions')
        app.register_blueprint(generator_bp, url_prefix='/generator')
        app.register_blueprint(mcq_bp, url_prefix='/mcq')
        app.register_blueprint(uploader_bp, url_prefix='/uploader')
        app.register_blueprint(student_bp, url_prefix='/student')

    @app.route("/")
    def index():
        from flask import render_template, flash
        from firebase_config import get_db
        db = get_db()
        try:
            papers_ref = db.collection('question_papers').stream()
            papers_by_subject = {}
            for paper_doc in papers_ref:
                paper = paper_doc.to_dict()
                subject_name = paper.get('subject_name', 'Unknown Subject')
                if subject_name not in papers_by_subject:
                    papers_by_subject[subject_name] = []
                papers_by_subject[subject_name].append(paper)
        except Exception as e:
            flash(f'Error fetching question papers: {e}', 'danger')
            papers_by_subject = {}
        return render_template('overview.html', papers_by_subject=papers_by_subject)

    return app

if __name__ == '__main__':
    # Entry point for running the Flask application
    app = create_app()
    app.run(debug=True, port=5000)
