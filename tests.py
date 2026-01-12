import unittest
import os
from app import create_app
from firebase_config import init_firebase, get_db

class FlaskTestCase(unittest.TestCase):

    def setUp(self):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.app.config['SECRET_KEY'] = 'test-secret-key'
        self.client = self.app.test_client()
        with self.app.app_context():
            init_firebase()
            self.db = get_db()

    def test_login_page(self):
        response = self.client.get('/admin/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admin Login', response.data)

    def test_dashboard_redirect_without_login(self):
        response = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admin Login', response.data)

if __name__ == '__main__':
    unittest.main()
