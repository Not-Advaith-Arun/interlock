"""Security property: report metadata cannot break out of text or JSON contexts."""
import json,re,unittest
from interlock.report_cards import render_report

class ReportEmbedding(unittest.TestCase):
    def test_untrusted_metadata_stays_literal_in_text_attributes_and_json(self):
        hostile='</script><img src=x onerror="window.injected=true"> & __SCRIPT__'
        document=render_report(hostile,hostile,['Value'],[{'group':hostile,'cells':[hostile]}],payload={'value':hostile})
        self.assertNotIn('<img src=x',document)
        self.assertIn('&lt;/script&gt;',document)
        raw=re.search(r'<script id="report-data" type="application/json">(.*?)</script>',document,re.S).group(1)
        self.assertEqual(json.loads(raw),{'value':hostile})
        self.assertEqual(document.count('<script>'),1)

if __name__=='__main__':unittest.main()
