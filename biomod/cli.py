"""biomod CLI dispatcher — argparse → handler in envs.py.

Step 1 wires only the env commands:
  biomod create -n <name>
  biomod activate <name>
  biomod deactivate
  biomod env list [--json]
  biomod env remove <name> [--yes]

Later steps will add: install / register / remove (step 3), list / info /
search (step 4), derive (step 5), run-begin / run-finish / run-fail
(step 6), status / runs (step 7). The `argparse` subparsers stay the
same shape — adding new commands extends the tree without disturbing
step 1.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import envs
from .exit_codes import SUCCESS, USER_ERROR
from . import __version__


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="biomod",
        description="Module catalog + package manager for bioinformatics analyses (v0 step 1).",
    )
    ap.add_argument("--version", action="version", version=f"biomod {__version__}")
    sub = ap.add_subparsers(dest="verb", metavar="<command>", required=True)

    # create
    p_create = sub.add_parser("create", help="create a new env")
    p_create.add_argument("-n", "--name", required=True, help="env name")

    # activate
    p_act = sub.add_parser("activate",
        help="print a shell snippet that sets $BIOMOD_ENV (use: eval \"$(biomod activate <name>)\")")
    p_act.add_argument("name", help="env name")

    # deactivate
    sub.add_parser("deactivate", help="print a shell snippet that unsets $BIOMOD_ENV")

    # env list / env remove (nested subparser)
    p_env = sub.add_parser("env", help="env-level operations")
    env_sub = p_env.add_subparsers(dest="env_verb", metavar="<subcommand>", required=True)

    p_env_list = env_sub.add_parser("list", help="list all envs")
    p_env_list.add_argument("--json", action="store_true",
                             help="emit JSON to stdout instead of a table")

    p_env_rm = env_sub.add_parser("remove", help="delete an env")
    p_env_rm.add_argument("name", help="env name")
    p_env_rm.add_argument("--yes", action="store_true",
                          help="skip interactive confirmation")

    return ap


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.verb == "create":
        return envs.cmd_create(args.name)
    if args.verb == "activate":
        return envs.cmd_activate(args.name)
    if args.verb == "deactivate":
        return envs.cmd_deactivate()
    if args.verb == "env":
        if args.env_verb == "list":
            return envs.cmd_env_list(as_json=args.json)
        if args.env_verb == "remove":
            return envs.cmd_env_remove(args.name, yes=args.yes)

    # argparse should have caught this — defensive
    print(f"unknown command: {args.verb}", file=sys.stderr)
    return USER_ERROR


if __name__ == "__main__":
    sys.exit(main())
