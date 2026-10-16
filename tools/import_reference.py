"""Create a local, filtered analysis snapshot. Never commits or pushes files."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import uuid4

EXCLUDED_DIRS = {
    '.git', '.svn', '.hg', 'node_modules', 'vendor', '.venv', 'venv',
    '__pycache__', '.vs', '.idea', 'obj', 'dist', 'build', 'target', 'coverage',
    '.next', '.nuxt', '.gradle', 'logs', 'log', 'tmp', 'temp', 'uploads',
    'backups', 'backup', 'datasets', 'testresults', 'packages',
}
ALLOWED_EXTENSIONS = {
    '.cs', '.csproj', '.sln', '.slnx', '.props', '.targets', '.razor', '.cshtml',
    '.vb', '.vbproj', '.fs', '.fsproj', '.java', '.kt', '.kts', '.gradle',
    '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.vue', '.svelte', '.html',
    '.css', '.scss', '.less', '.py', '.pyi', '.go', '.mod', '.sum', '.rs',
    '.rb', '.php', '.dart', '.swift', '.m', '.h', '.c', '.cpp', '.hpp',
    '.json', '.xml', '.config', '.yaml', '.yml', '.toml', '.ini', '.cfg',
    '.lock', '.md', '.rst', '.txt', '.sh', '.ps1', '.bat', '.cmd',
    '.graphql', '.gql', '.proto', '.properties',
}
ALLOWED_NAMES = {
    'dockerfile', 'makefile', 'gemfile', 'rakefile', 'procfile',
    '.gitignore', '.gitattributes', '.editorconfig', '.dockerignore',
    '.env.example', '.env.sample', '.env.template', 'license', 'notice',
}
DENIED_NAMES = re.compile(
    r'(?i)(^\.env($|\.(?!example$|sample$|template$))|'
    r'^id_(rsa|dsa|ecdsa|ed25519)(\.|$)|'
    r'^(credentials|secrets?|service[-_]?account)(\.|$)|'
    r'(^|[._-])(production|prod|local)\.(json|ya?ml|config|ini|properties)$|'
    r'^(\.npmrc|\.pypirc|\.netrc|nuget\.config|web\.config)$)'
)
SECRET_PATTERNS = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    re.compile(r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}\b'),
    re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'),
    re.compile(r'(?i)(?:password|pwd)\s*=\s*[^;\s\"\'<>]{3,}'),
    re.compile(r'''(?ix)["'](?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|client[_-]?secret)["']\s*[:=]\s*["'](?!["']|<|\$\{|\{\{|YOUR_|REPLACE_|EXAMPLE_|PLACEHOLDER|CHANGEME|example|dummy|test|xxx)[^"'\r\n]{3,}["']'''),
]
MAX_BYTES = 2 * 1024 * 1024


def in_tree(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def text_content(raw: bytes) -> str | None:
    # UTF-16 configuration files must be checked too, not silently decoded as UTF-8.
    try:
        if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
            return raw.decode('utf-16')
        if b'\0' in raw:
            return None
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            return raw.decode('gb18030')
        except UnicodeDecodeError:
            return None


def choose_file(path: Path) -> str | None:
    name = path.name.lower()
    if DENIED_NAMES.search(name):
        return 'sensitive_or_environment_filename'
    if name not in ALLOWED_NAMES and path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return 'outside_text_source_allowlist'
    return None


def import_snapshot(source: Path, target: Path, name: str = 'legacy') -> dict:
    source_info = source.lstat()
    if source.is_symlink() or getattr(source_info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Source must not be a symbolic link or junction.')
    source = source.resolve(strict=True)
    target = target.resolve()
    if not source.is_dir():
        raise ValueError('Source must be an existing project directory.')
    if source == Path(source.anchor):
        raise ValueError('Choose a project folder, not an entire drive.')
    if in_tree(target, source) or in_tree(source, target):
        raise ValueError('Source and target must be separate, non-nested folders.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', name):
        raise ValueError('Name must contain 1-48 ASCII letters, digits, underscores or hyphens.')
    target.mkdir(parents=True, exist_ok=True)
    # Never follow a reference-directory link out of the requested target.
    reference = target / 'reference'
    reference.mkdir(exist_ok=True)
    if reference.is_symlink() or not in_tree(reference.resolve(), target):
        raise ValueError('Target reference folder must be a real folder inside target.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    snapshot = reference / (name + '-' + stamp + '-' + uuid4().hex[:8])
    snapshot.mkdir(exist_ok=False)
    copied = []
    skipped = []
    for root, dirs, files in os.walk(source, topdown=True, followlinks=False):
        root = Path(root)
        safe_dirs = []
        for directory in sorted(dirs):
            path = root / directory
            rel = path.relative_to(source).as_posix()
            info = path.lstat()
            if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                skipped.append({'path': rel, 'reason': 'link_or_junction'})
            elif directory.lower() in EXCLUDED_DIRS or (
                directory.lower() == 'bin' and any(root.glob('*.csproj'))
            ):
                skipped.append({'path': rel + '/', 'reason': 'excluded_directory'})
            else:
                safe_dirs.append(directory)
        dirs[:] = safe_dirs
        for filename in sorted(files):
            path = root / filename
            rel = path.relative_to(source).as_posix()
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                    skipped.append({'path': rel, 'reason': 'not_regular_file'})
                    continue
                reason = choose_file(path)
                if reason:
                    skipped.append({'path': rel, 'reason': reason})
                    continue
                if info.st_size > MAX_BYTES:
                    skipped.append({'path': rel, 'reason': 'over_2_mib_requires_review'})
                    continue
                raw = path.read_bytes()
                decoded = text_content(raw)
                if decoded is None:
                    skipped.append({'path': rel, 'reason': 'binary_or_unknown_encoding'})
                    continue
                if any(pattern.search(decoded) for pattern in SECRET_PATTERNS):
                    skipped.append({'path': rel, 'reason': 'possible_embedded_secret_requires_review'})
                    continue
                destination = snapshot / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open('xb') as stream:
                    stream.write(raw)
                copied.append({'path': rel, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
            except OSError:
                skipped.append({'path': rel, 'reason': 'read_or_copy_error'})
    manifest = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Filtered analysis reference; not a deployable backup or a secret-free guarantee.',
        'source_label': source.name,
        'copied_count': len(copied), 'skipped_count': len(skipped),
        'copied': copied, 'skipped': skipped,
        'requires_human_review_before_sharing': True,
        'committed': False, 'pushed': False,
    }
    (snapshot / 'import-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (snapshot / 'IMPORT_NOTICE.txt').write_text(
        'LOCAL ANALYSIS SNAPSHOT. Source files were not modified.\n'
        'Dependencies, environment configs, binary data and likely secrets were filtered.\n'
        'This is NOT a full deployable copy. Review skipped files and all included content.\n'
        'Automated filtering does not guarantee absence of confidential information.\n'
        'No git add, commit, push, deployment, or source-code execution was performed.\n'
        'reference/ is excluded by the supplied .gitignore.\n', encoding='utf-8')
    return {'snapshot': str(snapshot), 'copied_count': len(copied), 'skipped_count': len(skipped), 'pushed': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--name', default='legacy')
    args = parser.parse_args()
    try:
        result = import_snapshot(args.source, args.target, args.name)
    except (OSError, ValueError):
        # Do not print source content or potentially sensitive exception messages.
        print('Import failed. Check folder paths, nesting, permissions, and import name.', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['copied_count'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
