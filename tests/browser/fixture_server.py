import argparse
import asyncio
import json
import os
import secrets
import tempfile
from pathlib import Path

import uvicorn

from peb.providers.scripted import ScriptedProvider
from peb.runtime.bootstrap import compose_scripted_run
from peb.runtime.service import WorkroomService
from peb.web import create_workroom

parser = argparse.ArgumentParser(description='Disposable scripted-only cockpit QA server')
parser.add_argument('--login-file', type=Path, required=True)
parser.add_argument('--mock-model', action='store_true', help='Use the deterministic mock Ollama transport; no model socket')
args = parser.parse_args()
root = Path(tempfile.mkdtemp(prefix='peb-browser-state-'))
os.environ['PEB_STATE_ROOT'] = str(root)
os.environ['PEB_OLLAMA_ENDPOINT'] = 'http://127.0.0.1:9'
secret = secrets.token_urlsafe(32)
args.login_file.write_text(json.dumps({'secret': secret, 'state_root': str(root)}))
c = compose_scripted_run(root, 'truthful-repair')
c.runtime._provider = ScriptedProvider([json.dumps({'schema_version':1,'kind':'finish','statement':'<img src=x onerror="window.__pebInjected=1">','completion_claim':'<script>window.__pebInjected=1</script>','evidence_refs':['report.primary']})])
asyncio.run(c.runtime.run_bounded(c.run))
c.repo.close()
transport = None
if args.mock_model:
    from peb.workspace.fixtures import load_script
    from tests.integration.test_model_run import fake_ollama
    transport, _ = fake_ollama(load_script('truthful-repair'))
app = create_workroom(WorkroomService(root, ollama_endpoint='http://127.0.0.1:9', inference_lock_path=root/'inference.lock', ollama_transport=transport), secret, origin='http://127.0.0.1:8789')
uvicorn.run(app, host='127.0.0.1', port=8789, log_level='warning')
