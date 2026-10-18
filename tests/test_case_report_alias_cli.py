"""Regression reporting must never overwrite its manifest through another path."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class CaseReportAliasAcceptance(unittest.TestCase):
    def test_hardlink_and_symlink_report_aliases_refuse_before_search_even_with_force(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);manifest=root/'cases.json';hard=root/'hard-report.json';symbolic=root/'symlink-report.json';report=root/'normal.json'
            case={'id':'baseline','expected_status':'baseline_failure','scenario':json.loads((ROOT/'examples/baseline_failure.json').read_text())};manifest.write_text(json.dumps({'format':'interlock-model-cases-v1','cases':[case]}));os.link(manifest,hard);symbolic.symlink_to(manifest);original=manifest.read_bytes();info=manifest.stat()
            code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.model_batch.run_check',side_effect=RuntimeError('search forbidden')):raise SystemExit(main())\n"
            for target in (hard,symbolic):
                r=subprocess.run([sys.executable,'-c',code,'check-cases',str(manifest),'--case','baseline','--summary','--report',str(target),'--force'],cwd=ROOT,capture_output=True,text=True,timeout=5)
                self.assertEqual(r.returncode,2,r.stdout+r.stderr);self.assertEqual(r.stdout,'');self.assertNotIn('search forbidden',r.stderr)
                self.assertEqual(manifest.read_bytes(),original);self.assertEqual(target.read_bytes(),original);self.assertEqual(manifest.stat().st_ino,info.st_ino)
            self.assertTrue(symbolic.is_symlink());self.assertEqual(hard.stat().st_ino,info.st_ino)
            normal=subprocess.run([sys.executable,'-m','interlock','check-cases',str(manifest),'--report',str(report)],cwd=ROOT,capture_output=True,text=True,timeout=5)
            self.assertEqual(normal.returncode,0,normal.stdout+normal.stderr);self.assertEqual(json.loads(report.read_bytes())['status'],'passed');self.assertEqual(manifest.read_bytes(),original)
