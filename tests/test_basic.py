import unittest
from app import create_app, db
from app.models.user import User

class BasicTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.drop_all()

    def test_index(self):
        rv = self.client.get('/')
        self.assertEqual(rv.status_code, 200)
        self.assertIn(b'Help Lagbe', rv.data)

    def test_submit_page(self):
        rv = self.client.get('/submit')
        self.assertEqual(rv.status_code, 200)

if __name__ == '__main__':
    unittest.main()
