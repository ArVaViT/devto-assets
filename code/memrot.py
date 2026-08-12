#!/usr/bin/env python3
"""memrot - find rot in an AI agent's file-based memory.

Memory files state facts. Facts decay. This walks every claim that can be
checked against the machine right now and reports the ones that no longer hold.

Usage: memrot.py <memory-dir> [--index MEMORY.md] [--op] [--net]
"""
import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

TODAY = dt.date.today()

# A filesystem path, not an API route. Anchored to roots that exist on a Mac,
# or an explicitly relative path. /api/... and /health are URLs and must not match.
# Absolute paths only. A relative path resolves against a working directory we
# do not know, so it cannot be checked and must not be guessed at.
RE_PATH = re.compile(
    r'`(~/[^`\s]{2,}|'
    r'/(?:Users|Applications|Volumes|opt|etc|usr|private|var|Library)/[^`\s]{2,})`')
# A command invocation: argv[0] plus an argument. argv[0] must additionally be a
# known CLI or carry a flag - otherwise `sql duplicate` and `h-11 h-7` look like
# commands, and the tool cries wolf.
RE_CMD = re.compile(r'`([a-z][a-z0-9_-]{1,20})\s+([^`]{1,60})`')
KNOWN_CLI = {
    'op', 'gh', 'git', 'brew', 'npm', 'npx', 'pnpm', 'yarn', 'node', 'deno',
    'python', 'python3', 'pip', 'pip3', 'pipx', 'uv', 'ruff', 'pytest',
    'supabase', 'vercel', 'docker', 'kubectl', 'terraform', 'aws', 'gcloud',
    'curl', 'wget', 'jq', 'yq', 'rg', 'fd', 'sed', 'awk', 'grep', 'find',
    'ssh', 'scp', 'rsync', 'cp', 'mv', 'rm', 'ls', 'cat', 'mkdir', 'chmod',
    'chflags', 'xattr', 'tccutil', 'defaults', 'launchctl', 'codesign', 'stat',
    'sqlite3', 'psql', 'mysql', 'redis-cli', 'ffmpeg', 'exiftool', 'convert',
    'make', 'cargo', 'go', 'ruby', 'gem', 'bundle', 'swift', 'xcodebuild',
    'claude', 'anki', 'osascript', 'plutil', 'diskutil', 'softwareupdate',
}
# 1Password item ids are 26 chars of lowercase base32
RE_OPID = re.compile(r'\b([a-z2-7]{26})\b')
RE_OPURI = re.compile(r'op://([^\s"\'`)]+)')
RE_WIKI = re.compile(r'\[\[([^\]]+)\]\]')
RE_URL = re.compile(r'https?://[^\s`"\'<>)\]]+')
# dd.mm.yyyy - the way this user writes dates in memory
RE_DATE = re.compile(r'\b(\d{2})\.(\d{2})\.(20\d{2})\b')
RE_MODIFIED = re.compile(r'^\s*modified:\s*(\S+)', re.M)
RE_NAME = re.compile(r'^\s*name:\s*(\S+)', re.M)

# commands we should not shell out to check, and words that only look like commands
CMD_NOISE = {
    'name', 'type', 'true', 'false', 'null', 'main', 'test', 'id', 'key', 'url',
    'http', 'https', 'api', 'app', 'src', 'dev', 'prod', 'db', 'ok', 'no', 'yes',
}


def toks(s: str) -> int:
    """Rough token count. Good enough for a budget, deliberately not exact."""
    return len(s) // 4


def load(memdir: str, index_name: str):
    files, index = [], None
    for fn in sorted(os.listdir(memdir)):
        if not fn.endswith('.md'):
            continue
        p = os.path.join(memdir, fn)
        body = open(p, encoding='utf-8').read()
        if fn == index_name:
            index = (fn, body)
        else:
            files.append((fn, body))
    return files, index


def expand(p: str) -> str:
    return os.path.expanduser(p.rstrip('.,;:)'))


def check_paths(body: str):
    bad = []
    for m in RE_PATH.finditer(body):
        raw = m.group(1)
        p = expand(raw)
        # a path with a glob or a placeholder is a pattern, not a claim
        if any(c in p for c in '*?<>{}') or p.endswith('/...'):
            continue
        if not os.path.exists(p):
            bad.append(raw)
    return bad


def check_cmds(body: str, cache: dict):
    bad = []
    for m in RE_CMD.finditer(body):
        c, rest = m.group(1), m.group(2)
        if c in CMD_NOISE or '.' in c or '/' in c:
            continue
        # Either a name we know is a CLI, or something carrying a real flag.
        if c not in KNOWN_CLI and not re.match(r'-{1,2}[a-z]', rest.strip()):
            continue
        if c not in cache:
            cache[c] = shutil.which(c) is not None
        if not cache[c]:
            bad.append(c)
    return bad


def check_op(body: str, cache: dict):
    """Ask 1Password whether the referenced items still exist. Read-only."""
    bad = []
    ids = set(RE_OPID.findall(body))
    for i in ids:
        if i not in cache:
            # An id can name an item or a vault. Ask about both before calling
            # it dead, or every vault reference reads as rot.
            ok = False
            for sub in (['item', 'get', i], ['vault', 'get', i]):
                r = subprocess.run(['op'] + sub + ['--format=json'],
                                   capture_output=True, text=True)
                if r.returncode == 0:
                    ok = True
                    break
            cache[i] = ok
        if not cache[i]:
            bad.append(i)
    return bad


# A deadline marker must sit immediately before the date. "с 06.08" is a log
# entry and means nothing expired; "до 19.10" is a claim with a shelf life.
RE_DEADLINE = re.compile(
    r'(?:истека\w*|истёк\w*|истек\w*|действ\w*\s+до|до|по|expires?(?:\s+on)?|'
    r'valid\s+(?:until|through)|until|deadline|renew\w*\s+by)\s*'
    r'(\d{2}\.\d{2}\.20\d{2})', re.I)


def check_dates(body: str):
    """Dates presented as a shelf life that the calendar has already passed."""
    past = []
    for m in RE_DEADLINE.finditer(body):
        d, mo, y = (int(x) for x in m.group(1).split('.'))
        try:
            when = dt.date(y, mo, d)
        except ValueError:
            continue
        if when < TODAY:
            past.append((m.group(1), (TODAY - when).days))
    return past


def check_urls(body: str, cache: dict, enabled: bool):
    if not enabled:
        return []
    bad = []
    for u in set(RE_URL.findall(body)):
        u = u.rstrip('.,;:)')
        if u not in cache:
            r = subprocess.run(
                ['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}',
                 '--max-time', '12', '-L', '-A', 'memrot/1.0', u],
                capture_output=True, text=True)
            cache[u] = r.stdout.strip()
        code = cache[u]
        if code in ('000', '404', '410'):
            bad.append((u, code))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('memdir')
    ap.add_argument('--index', default='MEMORY.md')
    ap.add_argument('--op', action='store_true', help='verify 1Password item ids')
    ap.add_argument('--net', action='store_true', help='verify URLs over the network')
    a = ap.parse_args()

    files, index = load(a.memdir, a.index)
    if not files:
        sys.exit(f'no memory files in {a.memdir}')

    names = {os.path.splitext(f)[0] for f, _ in files}
    ccache, opcache, ucache = {}, {}, {}
    findings = {}
    expired = []
    stale_days = []

    for fn, body in files:
        f = {}
        if p := check_paths(body):
            f['dead paths'] = p
        if c := check_cmds(body, ccache):
            f['missing commands'] = c
        if a.op and (o := check_op(body, opcache)):
            f['gone from 1Password'] = o
        # An expired date is not a false claim - the note may be describing the
        # past on purpose. It is a claim whose shelf life ran out, tracked apart.
        for x, n in check_dates(body):
            expired.append((fn, x, n))
        if w := [l for l in RE_WIKI.findall(body) if l not in names]:
            f['broken links'] = w
        if a.net and (u := check_urls(body, ucache, True)):
            f['dead urls'] = [f'{x} [{c}]' for x, c in u]
        if f:
            findings[fn] = f
        if m := RE_MODIFIED.search(body):
            try:
                d = dt.datetime.fromisoformat(m.group(1).replace('Z', '+00:00')).date()
                stale_days.append((fn, (TODAY - d).days))
            except ValueError:
                pass

    total = sum(len(b) for _, b in files)
    print('=' * 66)
    print('MEMORY AUDIT'.center(66))
    print('=' * 66)
    print(f'memory files      {len(files)}')
    print(f'total memory      {total:,} chars  (~{total//4:,} tokens)')
    if index:
        ib = index[1]
        print(f'index {index[0]:<12}{len(ib):,} chars  (~{toks(ib):,} tokens) '
              f'<- paid on EVERY session')
        print(f'cost per entry    ~{toks(ib)//max(1,len(files))} tokens of index per remembered fact')
    if stale_days:
        ages = sorted(d for _, d in stale_days)
        print(f'age of claims     median {ages[len(ages)//2]}d, oldest {ages[-1]}d '
              f'since last verification')
    print()

    if expired:
        print(f'SHELF LIFE EXPIRED: {len(expired)} dated claim(s) are past their own horizon')
        for fn, x, n in sorted(expired, key=lambda t: -t[2]):
            print(f'    {fn:<42} {x}  ({n}d ago)')
        print()

    if not findings:
        print('No rot found. Every checkable claim still holds.')
        return

    rotten = len(findings)
    print(f'ROTTEN: {rotten}/{len(files)} files ({100*rotten//len(files)}%) '
          f'contain at least one claim that is no longer true')
    print('-' * 66)
    kinds = Counter(k for f in findings.values() for k in f)
    for k, n in kinds.most_common():
        print(f'  {k:<24}{n} file(s)')
    print('-' * 66)
    for fn, f in sorted(findings.items()):
        print(f'\n{fn}')
        for kind, items in f.items():
            for it in items[:6]:
                print(f'    {kind:<22} {it}')
            if len(items) > 6:
                print(f'    {"":<22} ... +{len(items)-6} more')


if __name__ == '__main__':
    main()
