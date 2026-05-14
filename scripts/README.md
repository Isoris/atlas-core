# scripts/

Stdlib-only CLIs for the atlas-core action pipeline. No `pip install`,
no virtualenv — they run on whichever Python boots `atlas_server.py`.

## `atlas_action.py`

Bridges "the wiring is in" → "I can run analyses from a terminal".
Maps 1:1 onto the four endpoints in [server/atlas_server.py](../server/atlas_server.py):

| Subcommand | Hits | Purpose |
|---|---|---|
| `submit`   | `POST /api/actions`               | run a manifest, print produced layer_ids |
| `log`      | `GET /api/actions/{action_id}`    | read the latest action log entry |
| `list`     | `GET /api/layers`                 | filter the envelope index |
| `get`      | `GET /api/layers/{layer_id}`      | fetch one envelope |
| `new-id`   | (local)                           | print a schema-conformant action_id |

### Server URL precedence

`--server <url>` &nbsp;>&nbsp; `$ATLAS_SERVER_URL` &nbsp;>&nbsp; `http://127.0.0.1:8000`

### Examples

```bash
# Submit a manifest from a file, against the default localhost server
python3 scripts/atlas_action.py submit -f manifest.json --atlas inversion

# Pipe a manifest in
cat manifest.json | python3 scripts/atlas_action.py submit --atlas inversion

# Print the manifest the CLI would POST, without sending
python3 scripts/atlas_action.py submit -f manifest.json --dry-run

# Submit + immediately fetch the produced envelopes (compact summary)
python3 scripts/atlas_action.py submit -f manifest.json --atlas inversion --fetch

# After a submit, fetch one full envelope as JSON
python3 scripts/atlas_action.py get fst_windows_main_226_hatchery_C_gar_LG28_abc

# Just the payload portion of an envelope
python3 scripts/atlas_action.py get fst_windows_…_abc --payload-only

# List the 10 most recent staging envelopes for one cohort
python3 scripts/atlas_action.py list \
    --layer-type relatedness_result --stage staging --limit 10

# Pipe-friendly: layer_ids only, one per line
python3 scripts/atlas_action.py list --layer-type fst_windows -q

# Read an action's log entry (status / produced_layers / error)
python3 scripts/atlas_action.py log act_1715000000000_a4b

# When status=error, show the trace
python3 scripts/atlas_action.py log act_1715000000000_a4b -v

# Generate a fresh action_id (matches ^act_[A-Za-z0-9_]+$)
python3 scripts/atlas_action.py new-id --tag abc
```

### Composability

`submit -q` and `list -q` print one `layer_id` per line so you can
chain via `xargs`:

```bash
# Fetch every fst_windows envelope produced today
python3 scripts/atlas_action.py list --layer-type fst_windows -q \
  | xargs -L1 python3 scripts/atlas_action.py get --payload-only \
  > today_fst_payloads.jsonl

# Re-submit a known manifest and pipe layer_ids into another script
python3 scripts/atlas_action.py submit -f m.json --atlas inversion -q \
  | xargs -L1 echo "wrote layer:"
```

### Dependencies

Pure stdlib: `urllib.request`, `json`, `argparse`, `os`, `sys`, `time`,
`random`, `string`. Works on Windows + WSL + macOS + Linux without
setup.
