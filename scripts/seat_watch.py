#!/usr/bin/env python3
"""seat_watch.py — line-anchored CALLING name-watch over a sibling seat's transcript.

Reads three JSONL shapes on this machine:
  Claude Code : ~/.claude/projects/<cwd-key>/<session>.jsonl      (type user/assistant, queue-operation)
  Grok Build  : ~/.grok/sessions/<cwd-key>/<session>/chat_history.jsonl  (role user/assistant)
  Codex       : ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl      (type response_item, payload.role)

Emits one line per event:
  [watching] <label> ...                    heartbeat at start and every 30 min — verify it before trusting the watch
  [<label> user] <text>                     the human's prompts to that seat (mid-turn included for Claude)
  [<label> CALLING] <line> | <context>      assistant text whose LINE STARTS with CALLING <designation> (echo-damped)

Byte-offset tailer: never advances past an incomplete line (a read that lands mid-JSON
holds position; the completed line is parsed on the next pass). Truncation resets to 0.

Usage:
  seat_watch.py <transcript.jsonl> <label> <call-regex> [--no-users] [--once] [--from-start]
    --once        scan the whole file, print matches, exit (verification)
    --from-start  tail from byte 0 instead of the current end
The call-regex is applied with re.MULTILINE to assistant text, e.g.
  '^\\s*\\**CALLING\\s+(1/3|seat\\s*1/3|fable|claude)\\b'
"""
import json
import os
import re
import sys
import time

HEARTBEAT_S = 1800
POLL_S = 2

def texts_from_content(c):
    if isinstance(c, str):
        return [c]
    out = []
    if isinstance(c, list):
        for x in c:
            if isinstance(x, dict) and isinstance(x.get('text'), str):
                out.append(x['text'])
            elif isinstance(x, str):
                out.append(x)
    return out

def classify(m):
    """-> (role, text) with role in {'user','assistant'} or (None, None)."""
    # Claude Code
    t = m.get('type')
    if t in ('user', 'assistant') and isinstance(m.get('message'), dict):
        return t, '\n'.join(texts_from_content(m['message'].get('content')))
    if t == 'queue-operation' and m.get('operation') == 'enqueue':
        c = m.get('content') if isinstance(m.get('content'), str) else m.get('text') or m.get('prompt')
        if isinstance(c, str):
            return 'user', c
        return None, None
    # Codex
    if t == 'response_item' and isinstance(m.get('payload'), dict):
        p = m['payload']
        if p.get('type') == 'message' and p.get('role') in ('user', 'assistant'):
            return p['role'], '\n'.join(texts_from_content(p.get('content')))
        return None, None
    # Grok — role lives under `type`, content is str or [{type:text,text}]; no `message` key
    r = m.get('role') or (t if t in ('user', 'assistant') and 'message' not in m else None)
    if r in ('user', 'assistant'):
        txt = '\n'.join(texts_from_content(m.get('content')))
        txt = re.sub(r'^\s*<user_query>\s*|\s*</user_query>\s*$', '', txt)
        return r, txt
    return None, None

def one_line(s, n=220):
    s = ' '.join(s.split())
    return s if len(s) <= n else s[:n] + '…'

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    if len(args) < 3:
        sys.exit(__doc__)
    path, label, pat = args[0], args[1], args[2]
    rx = re.compile(pat, re.MULTILINE)
    emit_users = '--no-users' not in flags
    once = '--once' in flags

    def handle(line):
        try:
            m = json.loads(line)
        except Exception:  # noqa: BLE001 — a bad record must never kill the watch
            return
        role, txt = classify(m)
        if not role or not txt or not txt.strip():
            return
        if role == 'user' and emit_users:
            s = txt.strip()
            if s.startswith('<'):          # <system-reminder>, <task-notification>, tool results
                return
            print(f"[{label} user] {one_line(s)}", flush=True)
        elif role == 'assistant':
            for mm in rx.finditer(txt):
                start = txt.rfind('\n', 0, mm.start()) + 1
                end = txt.find('\n', mm.end())
                end = len(txt) if end == -1 else end
                ctx = txt[end:end + 300]
                print(f"[{label} CALLING] {one_line(txt[start:end], 300)} | {one_line(ctx, 300)}", flush=True)

    if once:
        with open(path, 'rb') as f:
            for raw in f:
                handle(raw.decode('utf-8', 'replace'))
        return

    off = 0 if '--from-start' in flags else os.path.getsize(path)
    print(f"[watching] {label} {path} from byte {off} pattern={pat}", flush=True)
    last_hb = time.time()
    # No carry buffer. The offset advances ONLY through the last complete newline;
    # a partial tail is simply re-read on the next pass. (Found by seat 2/3, 2026-09-11:
    # the earlier version both rewound `off` to the buffered bytes AND prepended them,
    # doubling the partial line into unparseable JSON that was silently dropped.)
    while True:
        try:
            sz = os.path.getsize(path)
            if sz < off:                    # truncated / rotated
                off = 0
            if sz > off:
                with open(path, 'rb') as f:
                    f.seek(off)
                    chunk = f.read(sz - off)
                cut = chunk.rfind(b'\n')
                if cut != -1:               # else: no complete line yet — hold position
                    for raw in chunk[:cut].split(b'\n'):
                        if raw.strip():
                            handle(raw.decode('utf-8', 'replace'))
                    off += cut + 1          # only through the last complete newline
        except FileNotFoundError:
            print(f"[{label} gone] {path} missing", flush=True)
        except Exception as e:  # noqa: BLE001 — report and keep watching
            print(f"[{label} error] {e}", flush=True)
        if time.time() - last_hb >= HEARTBEAT_S:
            print(f"[watching] {label} alive, consumed {off} bytes", flush=True)
            last_hb = time.time()
        time.sleep(POLL_S)

if __name__ == '__main__':
    main()
