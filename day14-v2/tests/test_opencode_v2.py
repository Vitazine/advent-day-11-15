from tests.test_chat_api import ApiCase
from tests.support import chat_payload

class OpenCodeV2Tests(ApiCase):
    def test_completion_budget_alias_is_forwarded_as_one_limit(self):
        for both in (False,True):
            p=chat_payload();p['max_completion_tokens']=128
            if both:p['max_tokens']=128
            r=self.send(p)
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(self.provider.calls[-1]['max_tokens'],128)
            self.assertNotIn('max_completion_tokens',self.provider.calls[-1])
    def test_conflicting_or_invalid_budget_rejected(self):
        for value in (0,8193,True,1.5):
            p=chat_payload();p['max_completion_tokens']=value
            self.assertEqual(self.send(p).status_code,422)
        p=chat_payload();p.update(max_tokens=128,max_completion_tokens=256)
        self.assertEqual(self.send(p).status_code,422)
        self.assertEqual(self.provider.calls,[])
