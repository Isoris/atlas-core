#!/usr/bin/env python3
"""Balance check for JS files: strips strings/comments via state machine."""
import sys

def strip(src):
    mode = 'code'
    out = []
    i = 0
    n = len(src)
    # Previous non-whitespace code character — used to disambiguate
    # regex literals (/foo/g) from division. After ), ], identifier
    # or number, '/' means division; after operators, '(', '[', ',',
    # '=', 'return' etc., '/' starts a regex literal.
    prev = ''
    while i < n:
        c = src[i]
        nx = src[i+1] if i+1 < n else ''
        if mode == 'code':
            if c == '/' and nx == '/':
                mode = 'lc'; i += 2; continue
            if c == '/' and nx == '*':
                mode = 'bc'; i += 2; continue
            if c == '/':
                # Regex literal heuristic: division iff prev is closing
                # bracket, identifier-ish char, or digit. Anything else
                # (including empty prev = file start) → regex.
                is_div = prev in (')', ']', '}', '_') or prev.isalnum()
                if not is_div:
                    mode = 'regex'; i += 1; continue
                # Else: division — fall through to append.
            if c == "'":
                mode = 'str_s'; i += 1; continue
            if c == '"':
                mode = 'str_d'; i += 1; continue
            if c == '`':
                mode = 'tpl'; i += 1; continue
            if not c.isspace():
                prev = c
            out.append(c); i += 1
        elif mode == 'lc':
            if c == '\n':
                mode = 'code'; out.append(c)
            i += 1
        elif mode == 'bc':
            if c == '*' and nx == '/':
                mode = 'code'; i += 2; continue
            i += 1
        elif mode == 'str_s':
            if c == '\\':
                i += 2; continue
            if c == "'":
                mode = 'code'
            i += 1
        elif mode == 'str_d':
            if c == '\\':
                i += 2; continue
            if c == '"':
                mode = 'code'
            i += 1
        elif mode == 'tpl':
            if c == '\\':
                i += 2; continue
            if c == '$' and nx == '{':
                mode = 'tpl_expr'; i += 2; continue
            if c == '`':
                mode = 'code'
            i += 1
        elif mode == 'tpl_expr':
            if c == '}':
                mode = 'tpl'; i += 1; continue
            out.append(c); i += 1
        elif mode == 'regex':
            if c == '\\':
                i += 2; continue
            if c == '[':
                mode = 'regex_cls'; i += 1; continue
            if c == '/':
                # End of regex body. Consume optional flags.
                i += 1
                while i < n and src[i].isalpha():
                    i += 1
                mode = 'code'
                prev = ')'  # treat regex as a value, so next / is division
                continue
            i += 1
        elif mode == 'regex_cls':
            if c == '\\':
                i += 2; continue
            if c == ']':
                mode = 'regex'; i += 1; continue
            i += 1
    return ''.join(out)

if __name__ == '__main__':
    path = sys.argv[1]
    src = open(path).read()
    s = strip(src)
    bad = 0
    for a, b in [('(', ')'), ('{', '}'), ('[', ']')]:
        ca, cb = s.count(a), s.count(b)
        flag = '' if ca == cb else '  !! MISMATCH'
        if ca != cb:
            bad += 1
        print(f"{a}{b}: {ca} / {cb}{flag}")
    sys.exit(bad)
