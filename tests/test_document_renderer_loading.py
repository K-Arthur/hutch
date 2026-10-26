"""Missing native PDF libraries must not prevent unrelated assistant startup."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_missing_pdf_native_libraries_are_isolated_to_pdf_requests(tmp_path):
    script = textwrap.dedent('''
        import builtins
        import sys
        original = builtins.__import__
        def without_pdf(name, *args, **kwargs):
            if name == 'weasyprint' or name.startswith('weasyprint.'):
                raise OSError('synthetic missing native graphics library')
            return original(name, *args, **kwargs)
        builtins.__import__ = without_pdf
        import hutch.engine
        from hutch.documents.docgen import generate, supported_formats, renderer_unavailable_reason
        assert 'weasyprint' not in sys.modules
        assert 'pdf' in supported_formats()
        assert generate('csv', {'header': ['name'], 'rows': [['Cedar']]}).data
        assert renderer_unavailable_reason('csv') == ''
        reason = renderer_unavailable_reason('pdf')
        assert 'unavailable' in reason and 'synthetic' not in reason
        from hutch.documents.docgen import DocumentGenerationError
        try:
            generate('pdf', {'title': 'Unavailable', 'blocks': [{'p': 'draft'}]})
        except DocumentGenerationError as error:
            assert str(error) == reason
        else:
            raise AssertionError('PDF must fail clearly; no alternate format or native dependency fallback')
        from hutch.server.app import create_app
        app = create_app()
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            response = client.get('/api/v1/documents/readiness')
            assert response.status_code == 200
            formats = {row['format']: row for row in response.json()['formats']}
            assert formats['csv']['available'] is True
            assert formats['pdf']['available'] is False
            assert formats['pdf']['unavailable_reason'] == reason
    ''')
    env = {**os.environ, 'HUTCH_STATE_DIR': str(tmp_path / 'state'), 'HUTCH_ALLOWED_HOSTS': 'testserver'}
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
