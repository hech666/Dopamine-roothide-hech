#!/usr/bin/env python3
"""Resolve latest arm64e packages at build time; verify repository SHA256."""
import bz2, gzip, hashlib, json, lzma, pathlib, re, urllib.request
from functools import cmp_to_key
ROOT = pathlib.Path(__file__).resolve().parent

def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()

def compare_part(a, b):
    def order(c):
        if c == '~': return -1
        if not c or c.isdigit(): return 0
        return ord(c) if c.isalpha() else ord(c) + 256
    while a or b:
        while (a and not a[0].isdigit()) or (b and not b[0].isdigit()):
            x, y = order(a[:1]), order(b[:1])
            if x != y: return 1 if x > y else -1
            a, b = a[1:], b[1:]
        x, y = re.match(r'\d*', a)[0], re.match(r'\d*', b)[0]
        a, b = a[len(x):], b[len(y):]
        x, y = x.lstrip('0'), y.lstrip('0')
        if len(x) != len(y): return 1 if len(x) > len(y) else -1
        if x != y: return 1 if x > y else -1
    return 0

def compare(a, b):
    def split(v):
        epoch, rest = v.split(':', 1) if ':' in v else ('0', v)
        upstream, revision = rest.rsplit('-', 1) if '-' in rest else (rest, '0')
        return int(epoch), upstream, revision
    x, y = split(a['Version']), split(b['Version'])
    return (x[0] > y[0]) - (x[0] < y[0]) or compare_part(x[1], y[1]) or compare_part(x[2], y[2])

def resolve(base, package, output):
    errors = []
    for extension, decode in [('', lambda b: b), ('.xz', lzma.decompress), ('.bz2', bz2.decompress), ('.gz', gzip.decompress)]:
        try:
            text = decode(fetch(base + 'Packages' + extension)).decode()
            break
        except Exception as error:
            errors.append(str(error))
    else: raise RuntimeError('Cannot read index: ' + '; '.join(errors))
    candidates = []
    for block in re.split(r'\n\s*\n', text):
        fields = dict(line.split(': ', 1) for line in block.splitlines() if ': ' in line and not line[0].isspace())
        if fields.get('Package') == package and fields.get('Architecture') == 'iphoneos-arm64e':
            candidates.append(fields)
    if not candidates: raise RuntimeError('Missing package: ' + package)
    selected = max(candidates, key=cmp_to_key(compare))
    expected = selected.get('SHA256', '')
    if not re.fullmatch('[0-9a-fA-F]{64}', expected): raise RuntimeError('Missing SHA256: ' + package)
    data = fetch(urllib.parse.urljoin(base, selected['Filename']))
    if hashlib.sha256(data).hexdigest() != expected.lower(): raise RuntimeError('SHA256 mismatch: ' + package)
    temporary = ROOT / (output + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(ROOT / output)
    print(package, selected['Version'], expected)
    return {key: selected.get(key) for key in ['Package', 'Version', 'Architecture', 'Depends', 'Conflicts', 'Provides', 'SHA256']}

if __name__ == '__main__':
    manifest = [resolve('https://roothide.github.io/', 'preferenceloader', 'preferenceloader.deb'), resolve('https://huayuarc.github.io/', 'org.coolstar.libhooker', 'libhooker.deb')]
    (ROOT / 'builtin-packages.json').write_text(json.dumps(manifest, indent=2) + '\n')
