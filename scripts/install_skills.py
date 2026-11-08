#!/usr/bin/env python3
"""Install this repository's functional and first-run Skills using only stdlib."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


def inside(root, value):
    relative = Path(value)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Skill source must stay inside the repository')
    result = root / relative
    if root != result.resolve() and root not in result.resolve().parents:
        raise ValueError('Skill source escapes the repository')
    return result


def install(repo_root, skills_dir, dry_run=False):
    root = Path(repo_root).resolve()
    target_root = Path(skills_dir).expanduser().resolve()
    config = json.loads((root / 'onboarding.json').read_text(encoding='utf-8'))
    specs = config['skills']
    names = [s['name'] for s in specs]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate Skill destination')
    plans = []
    # Validate every source and destination before creating or replacing any Skill.
    for spec in specs:
        name = spec['name']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or len(name) > 64:
            raise ValueError('Invalid Skill name')
        source = inside(root, spec['path'])
        if source.is_symlink() or not (source / 'SKILL.md').is_file():
            raise ValueError('Skill source unavailable: ' + name)
        destination = target_root / name
        if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
            raise ValueError('Refusing to replace a linked or non-directory Skill: ' + name)
        if source == destination or source in destination.parents or destination in source.parents:
            raise ValueError('Installation source and destination overlap')
        paths = []
        for item in ['SKILL.md', 'agents', 'references', 'scripts', 'assets']:
            path = source / item
            if path.is_symlink():
                raise ValueError('Linked Skill resource is not supported: ' + name)
            if not path.exists():
                continue
            candidates = [path] if path.is_file() else path.rglob('*')
            for candidate in candidates:
                if candidate.is_symlink():
                    raise ValueError('Linked Skill resource is not supported: ' + name)
                if not candidate.is_file():
                    continue
                relative = candidate.relative_to(source)
                if '__pycache__' in relative.parts or candidate.suffix == '.pyc' or candidate.name == '.DS_Store':
                    continue
                if relative.as_posix() == 'scripts/install_skills.py':
                    continue
                paths.append((candidate, relative))
        plans.append((name, destination, paths))
    if dry_run:
        return [{'name': name, 'action': 'update' if dest.exists() else 'install'} for name, dest, _ in plans]
    target_root.mkdir(parents=True, exist_ok=True)
    results = []
    for name, destination, paths in plans:
        stage = Path(tempfile.mkdtemp(prefix='.skill-stage-', dir=target_root))
        backup = None
        try:
            for source, relative in paths:
                out = stage / relative
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, out)
            if name == config['setup_skill']:
                context = stage / 'references' / 'installation.json'
                context.parent.mkdir(parents=True, exist_ok=True)
                context.write_text(json.dumps({'repository': config['repository'], 'repository_path': str(root)},
                                              ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            if destination.exists():
                backups = target_root.parent / 'skill-backups'
                backups.mkdir(exist_ok=True)
                if backups.is_symlink():
                    raise ValueError('Backup directory must not be a symlink')
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                backup = backups / (name + '-' + stamp)
                destination.rename(backup)
            try:
                stage.rename(destination)
            except Exception:
                if backup is not None and not destination.exists():
                    backup.rename(destination)
                raise
            results.append({'name': name, 'destination': str(destination), 'backup': str(backup) if backup else None})
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
    parser.add_argument('--skills-dir', default=str(default_home / 'skills'))
    parser.add_argument('--dry-run', action='store_true', help='List planned Skills without writing files')
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    for result in install(repo_root, args.skills_dir, args.dry_run):
        print(json.dumps(result, ensure_ascii=False))
    if not args.dry_run:
        config = json.loads((repo_root / 'onboarding.json').read_text(encoding='utf-8'))
        print('Reopen your Codex task, then invoke $' + config['setup_skill'])
        print('Skills installed. Runtime dependencies, browser extension and account authorization are configured by the setup Skill.')


if __name__ == '__main__':
    main()
