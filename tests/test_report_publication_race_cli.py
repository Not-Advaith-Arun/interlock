"""Concurrent report publishers must keep the complete no-clobber winner."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ReportPublicationRaceAcceptance(unittest.TestCase):
    def test_destination_created_after_preflight_is_preserved_without_partial_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);ready=root/'ready';release=root/'release';report=root/'report.json'
            scenario=json.loads((ROOT/'examples/baseline_failure.json').read_text())
            for label in ('slow','winner'):(root/(label+'.json')).write_text(json.dumps({'format':'interlock-model-cases-v1','cases':[{'id':label,'expected_status':'baseline_failure','scenario':scenario}]}))
            code=("import os,sys,time;from pathlib import Path;from unittest.mock import patch;from interlock.cli import main\n"
                  "ready=Path(sys.argv.pop(1));release=Path(sys.argv.pop(1));original=os.link\n"
                  "def publish(*a,**k):\n"
                  " ready.touch();deadline=time.monotonic()+8\n"
                  " while not release.exists():\n"
                  "  if time.monotonic()>deadline:raise RuntimeError('publication barrier timeout')\n"
                  "  time.sleep(.01)\n"
                  " return original(*a,**k)\n"
                  "with patch('interlock.cli.os.link',publish):raise SystemExit(main())\n")
            slow=subprocess.Popen([sys.executable,'-c',code,str(ready),str(release),'check-cases',str(root/'slow.json'),'--report',str(report)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                deadline=time.monotonic()+5
                while not ready.exists() and slow.poll() is None and time.monotonic()<deadline:time.sleep(.01)
                self.assertTrue(ready.exists());self.assertFalse(report.exists())
                winner=subprocess.run([sys.executable,'-m','interlock','check-cases',str(root/'winner.json'),'--report',str(report)],cwd=ROOT,capture_output=True,text=True,timeout=5)
                self.assertEqual(winner.returncode,0,winner.stdout+winner.stderr);saved=report.read_bytes();self.assertEqual(json.loads(saved)['cases'][0]['id'],'winner')
                release.touch();out,err=slow.communicate(timeout=5);self.assertEqual(slow.returncode,2,out+err);self.assertEqual(out,'');self.assertEqual(report.read_bytes(),saved);self.assertEqual(list(root.glob('*.tmp')),[])
            finally:
                release.touch()
                if slow.poll() is None:slow.kill();slow.communicate()
