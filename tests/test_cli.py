"""Regression for Russian CLI text under a legacy Windows console encoding."""
import os
import subprocess
import sys
from pathlib import Path


def test_help_works_with_cp1252_stdout():
    environment = os.environ.copy()
    environment['PYTHONIOENCODING'] = 'cp1252'
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    result = subprocess.run(
        [sys.executable, '-m', 'livetranslate', '--help'],
        capture_output=True, env=environment, timeout=15,
    )
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    assert 'локальные' in result.stdout.decode('utf-8')
