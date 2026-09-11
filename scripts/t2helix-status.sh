#!/usr/bin/env bash
# t2helix-status — receipts for "is this seat on the latest t2helix and the shared chronicle?"
# Read-only. Safe to run from any seat.
set -u
DB="$HOME/.claude/plugins/data/t2helix-templetwo-t2helix/chronicle.db"
SHARD="colab-untitled-folder"
ver() { python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['version'])" "$1" 2>/dev/null || echo "?"; }

echo "host          : $(hostname)   user: $(whoami)"

INSTALL=$(python3 -c "import json;d=json.load(open('$HOME/.claude/plugins/installed_plugins.json'));print(d['plugins']['t2helix@templetwo-t2helix'][0]['installPath'])" 2>/dev/null)
echo "claude plugin : $(ver "$INSTALL/package.json")   $INSTALL"
if [ -f "$INSTALL/node_modules/better-sqlite3/build/Release/better_sqlite3.node" ]; then
  echo "                native driver: built ($(python3 -c "import json;d=json.load(open('$INSTALL/.native-abi.json'));print(d['node'],'ABI',d['modules'])" 2>/dev/null || echo 'no stamp'))"
else
  echo "                native driver: MISSING -> cd $INSTALL && npm run rebuild"
fi

echo "~/t2helix     : $(ver "$HOME/t2helix/package.json")   $(git -C "$HOME/t2helix" log -1 --format='%h %cs' 2>/dev/null)"
UP=$(git -C "$HOME/t2helix" ls-remote origin -h refs/heads/main 2>/dev/null | cut -c1-7)
echo "upstream main : ${UP:-unreachable}"

echo "grok config   : $(awk '/^\[mcp_servers.t2helix\]/{f=1} f&&/^args/{print; exit}' "$HOME/.grok/config.toml" 2>/dev/null | sed 's/args = //')"
echo "grok data dir : $(awk '/^\[mcp_servers.t2helix.env\]/{f=1} f&&/T2HELIX_DATA_DIR/{print; exit}' "$HOME/.grok/config.toml" 2>/dev/null | sed 's/.*= //')"

if grep -q 'mcp_servers.t2helix' "$HOME/.codex/config.toml" 2>/dev/null; then
  echo "codex config  : $(sed -n '/T2HELIX CODEX CONNECTOR >>>/,/<<< T2HELIX CODEX CONNECTOR/p' "$HOME/.codex/config.toml" | grep -E '^(command|args)' | tr '\n' ' ')"
else
  echo "codex config  : NOT REGISTERED -> cd ~/t2helix && PATH=\$HOME/.local/bin:\$PATH npm run codex:init"
fi

echo "chronicle db  : $DB"
if [ -f "$DB" ]; then
  sqlite3 -readonly "$DB" "SELECT '                insights: '||COUNT(*)||'   board('||'$SHARD'||'): '||SUM(domain='$SHARD') FROM insights;" 2>/dev/null
fi
