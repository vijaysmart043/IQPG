import firebase_admin
from firebase_admin import credentials, firestore, storage, auth
from datetime import datetime
import os

db = None
bucket = None

def init_firebase():
    """
    Initializes the Firebase Admin SDK.
    This function should be called once at the start of the application.
    """
    global db, bucket
    # Check if the app is already initialized to prevent errors
    if not firebase_admin._apps:
        try:
            # Get the path to the service account key from environment variables
            cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if not cred_path:
                raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")

            cred = credentials.Certificate(cred_path)
            
            # Normalize bucket name if a firebase web bucket string was provided
            raw_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
            if raw_bucket and raw_bucket.endswith('firebasestorage.app'):
                # Convert "<project>.firebasestorage.app" -> "<project>.appspot.com"
                project = raw_bucket.split('.')[0]
                normalized_bucket = f"{project}.appspot.com"
            else:
                normalized_bucket = raw_bucket

            # Initialize the app with optional storage bucket config
            init_options = {}
            if normalized_bucket:
                init_options['storageBucket'] = normalized_bucket
            firebase_admin.initialize_app(cred, init_options)
            
            print("Firebase initialized successfully.")
        except Exception as e:
            print(f"Error initializing Firebase: {e}")
            # Handle the error appropriately, maybe exit the app
            exit()

    # Get Firestore client and Storage bucket instances
    db = firestore.client()
    # Only create a Storage client if a bucket is configured
    try:
        default_bucket = firebase_admin.get_app().project_id  # touch app to ensure initialized
        # Read env again to determine if bucket exists
        env_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
        if env_bucket:
            # If provided, try to create a bucket handle; firebase_admin handles name from config
            bucket = storage.bucket()
        else:
            bucket = None
    except Exception:
        bucket = None
    print("Firestore and Storage clients are ready.")

def get_db():
    """Returns the Firestore database client instance."""
    if db is None:
        init_firebase()
    return db

def get_bucket():
    """Returns the Firebase Storage bucket instance."""
    if bucket is None:
        init_firebase()
    return bucket

def get_auth():
    """Returns the Firebase Auth client instance."""
    return auth


# Simple activity logger to Firestore (best-effort, non-blocking)
def log_activity(user_id: str, action: str, metadata: dict | None = None):
    try:
        client = get_db()
        entry = {
            'user_id': user_id,
            'action': action,
            'metadata': metadata or {},
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        client.collection('activity_logs').add(entry)
    except Exception:
        # Do not raise; logging should not break primary flows
        pass

