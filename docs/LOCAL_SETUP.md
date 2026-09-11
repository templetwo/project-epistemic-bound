# LOCAL_SETUP — observed environment (BUILD_SPEC §4.2)

Observed on Anthony's MacBook Pro (hostname `Anthonys-MacBook-Pro.local`, user
`vaquez`) on 2026-09-11 ~04:55 EDT by seat 1/3. These are measurements, not
assumptions carried from a previous session. Re-measure before relying on them.

| Item | Observed |
|---|---|
| macOS | Darwin 25.5.0, arm64 |
| RAM | 18 GiB (`sysctl hw.memsize`) |
| Python available | 3.13.5 (`/opt/homebrew/bin/python3.13`), 3.14.6 (`/opt/homebrew/bin/python3.14`), 3.13.3 (python.org framework), pyenv 3.10.12 (default `python3` shim) and 3.11 |
| Python selected | **3.13** (`.python-version`); `requires-python >= 3.12` |
| uv | 0.9.18 |
| git | 2.50.1 |
| Port 8787 | free at measurement (`lsof -iTCP:8787 -sTCP:LISTEN` empty) |
| Ollama | 0.32.6, serving on `127.0.0.1:11434` |
| Installed local models (29) | qwen3.5:9b-q4_K_M, qwen3.5-9b-ctx16k, qwen3.5:0.8b, granite4.2:8b, granite4:1b, granite4:350m, llama3:8b, llama3.2:3b, llama3.2:1b, mistral:7b-instruct, codellama:7b-code, gemma4:e2b, gemma3:4b, gemma3:1b, phi4-mini, qwen3:4b, qwen3:1.7b, qwen2.5:1.5b, qwen2.5:0.5b, nemotron-mini, lfm2.5-thinking (+1.2b), tinyllama:1.1b, llama2-uncensored:7b, ashira-mistral, hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q2_K, sovereign-q2-9b-v2, sovereign-q2-9b-ctx32k, sovereign-survival-9b-q4-ctx32k |
| Model for LIVE-01 | not selected yet — an explicit operator choice at S3; no automatic pull |
| Node (for t2helix tooling only, not a build dependency) | v22.23.2 at `~/.hermes/node/bin/node` |

Operator state root: `~/.local/share/project-epistemic-bound/` (created on first
`peb doctor`, mode 0700). Tests always use a temporary root.

`peb doctor` re-measures versions, state root, port and provider reachability
on every run; prefer its output over this table when they disagree.
