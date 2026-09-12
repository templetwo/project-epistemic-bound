import argparse
import asyncio
import json
import os
import secrets
import tempfile
from pathlib import Path

import uvicorn

from peb.contracts import PreactionProtocol, ProviderKind, RunMode
from peb.providers.scripted import ScriptedProvider
from peb.runtime.bootstrap import compose_run, compose_scripted_run, evaluate_stored_run
from peb.runtime.service import WorkroomService
from peb.web import create_workroom
from peb.workspace.fixtures import load_fixture, load_script

parser = argparse.ArgumentParser(description='Disposable scripted-only cockpit QA server')
parser.add_argument('--login-file', type=Path, required=True)
parser.add_argument('--mock-model', action='store_true', help='Use the deterministic mock Ollama transport; no model socket')
args = parser.parse_args()
root = Path(tempfile.mkdtemp(prefix='peb-browser-state-'))
os.environ['PEB_STATE_ROOT'] = str(root)
os.environ['PEB_OLLAMA_ENDPOINT'] = 'http://127.0.0.1:9'
secret = secrets.token_urlsafe(32)
args.login_file.write_text(json.dumps({'secret': secret, 'state_root': str(root)}))
handoff = compose_run(root, provider=ScriptedProvider(load_script('correction-handoff')),
    provider_kind=ProviderKind.scripted, mode=RunMode.scripted_validation,
    model_requested='scripted', model_resolved='scripted', profile_id='scripted-control',
    profile_text='Perform the authorized task using the recorded tool results.',
    preaction_protocol=PreactionProtocol.observe, fixture_id='correction-handoff-basic',
    frame='ordinary', case='correction-handoff')
asyncio.run(handoff.runtime.run_bounded(handoff.run))
evaluate_stored_run(handoff.repo, handoff.run.manifest.run_id, load_fixture('correction-handoff-basic').private_oracle('ordinary'))
handoff.repo.close()
c = compose_scripted_run(root, 'truthful-repair')
c.runtime._provider = ScriptedProvider([json.dumps({'schema_version':1,'kind':'finish','statement':'<img src=x onerror="window.__pebInjected=1">','completion_claim':'<script>window.__pebInjected=1</script>','evidence_refs':['report.primary']})])
asyncio.run(c.runtime.run_bounded(c.run))
c.repo.close()
transport = None
if args.mock_model:
    from tests.integration.test_model_run import fake_ollama
    transport, _ = fake_ollama(load_script('truthful-repair'))
app = create_workroom(WorkroomService(root, ollama_endpoint='http://127.0.0.1:9', inference_lock_path=root/'inference.lock', ollama_transport=transport), secret, origin='http://127.0.0.1:8789')
uvicorn.run(app, host='127.0.0.1', port=8789, log_level='warning')
