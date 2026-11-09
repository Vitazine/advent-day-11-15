import unittest
from gateway.openapi import schema
class OpenApiTests(unittest.TestCase):
    def test_contracts(self):
        s=schema();self.assertEqual(s['openapi'],'3.1.0')
        self.assertEqual(set(s['paths']),{'/v1/models','/v1/limits','/v1/chat/completions','/v1/security/reviews'})
        self.assertEqual(s['security'],[{'bearerAuth':[]}])
        self.assertIn('ChatRequest',s['components']['schemas'])
