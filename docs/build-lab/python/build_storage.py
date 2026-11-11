"""Local build snapshots, independent of browser download permissions."""
import json
import os
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

BUILD_DIR = Path(__file__).resolve().parent / '저장한 빌드'
LIMIT = 8 * 1024 * 1024


def validate(document):
    if not isinstance(document, dict) or document.get('format') != 'cte-build-lab' or document.get('version') != 1:
        raise ValueError('CTE 빌드 저장 파일이 아닙니다.')
    for key in ('a', 'b'):
        build = document.get(key)
        if not isinstance(build, dict) or not isinstance(build.get('sources'), list) or not isinstance(build.get('skills'), list):
            raise ValueError('A와 B 빌드의 장비·스킬 정보가 필요합니다.')
    if not isinstance(document.get('scenario', {}), dict):
        raise ValueError('전투 비교 설정이 올바르지 않습니다.')
    return document


def _path(filename):
    if not isinstance(filename, str) or not re.fullmatch(r'\d{8}-\d{6}-[0-9a-f]{32}_[^/\\\x00-\x1f]+\.json', filename):
        raise ValueError('저장 목록에서 빌드를 선택하세요.')
    path = BUILD_DIR / filename
    if path.resolve().parent != BUILD_DIR.resolve() or path.is_symlink():
        raise ValueError('저장 목록에서 빌드를 선택하세요.')
    return path


def read_build(filename):
    path = _path(filename)
    if not path.is_file():
        raise ValueError('저장한 빌드 파일을 찾지 못했습니다.')
    if path.stat().st_size > LIMIT:
        raise ValueError('빌드 파일은 8MB 이하여야 합니다.')
    return validate(json.loads(path.read_text(encoding='utf-8')))


def _entry(path, document):
    return {'id': path.name, 'name': str(document['a'].get('name') or 'A 빌드'),
            'comparison': str(document['b'].get('name') or 'B 빌드'),
            'modified': path.stat().st_mtime, 'filename': path.name}


def list_builds():
    rows = []
    for path in BUILD_DIR.glob('*.json'):
        try:
            rows.append(_entry(path, read_build(path.name)))
        except (ValueError, OSError):
            continue
    return sorted(rows, key=lambda row: (row['modified'], row['id']), reverse=True)


def save_build(document):
    validate(document)
    raw = json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
    if len(raw) > LIMIT:
        raise ValueError('빌드 파일은 8MB 이하여야 합니다.')
    name = str(document['a'].get('name') or 'CTE2 빌드')
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:60] or 'CTE2 빌드'
    filename = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S-') + uuid4().hex + '_' + name + '.json'
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    target = _path(filename)
    pending = target.with_suffix('.pending')
    try:
        with pending.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, target)
        # Only acknowledge success after reading the complete file back.
        if target.read_bytes() != raw:
            raise OSError('저장된 빌드 파일 확인에 실패했습니다.')
    finally:
        if pending.exists():
            pending.unlink()
    return {**_entry(target, document), 'folder': str(BUILD_DIR)}
