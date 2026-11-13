"""Build release assets only from the explicitly tracked managed client/server patch payloads."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, io, json, re, zipfile

ROOT = Path(__file__).resolve().parent
ALLOWED = {'mods', 'config', 'defaultconfigs', 'kubejs', 'patchouli_books', 'resourcepacks'}
ADDON = 'mods/CTE2-Multiplayer-1.20.1-0.1.0.jar'
REPO = 'https://github.com/piro0101/CTE2-Multi'


def stamp(raw, release_id):
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        assert source.testzip() is None
        assert b'kr/cte2/multi/ReleaseVersion' in source.read('kr/cte2/multi/ConfigSync.class')
        assert 'kr/cte2/multi/ReleaseVersion.class' in source.namelist()
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as target:
            for name in sorted(source.namelist()):
                data = (release_id + '\n').encode() if name == 'cte2_release.txt' else source.read(name)
                entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                target.writestr(entry, data)
        result = out.getvalue()
    with zipfile.ZipFile(io.BytesIO(result)) as target, zipfile.ZipFile(io.BytesIO(raw)) as source:
        assert target.testzip() is None
        assert target.read('cte2_release.txt').decode().strip() == release_id
        assert all(target.read(n) == source.read(n) for n in source.namelist() if n != 'cte2_release.txt')
    return result


def build(release_id, tag):
    assert re.fullmatch(r'[a-zA-Z0-9._-]{1,64}', release_id)
    assert re.fullmatch(r'[a-zA-Z0-9._-]{1,80}', tag)
    output = ROOT / 'dist/release'
    output.mkdir(parents=True, exist_ok=True)
    digest = lambda b: hashlib.sha256(b).hexdigest()
    manifest = {'schema': 1, 'release_id': release_id, 'minimum_patcher': '1.1.0',
                'notes': (ROOT / 'release/notes.md').read_text('utf-8'), 'packages': {}}
    game = json.loads((ROOT / 'release/game-version.json').read_text('utf-8'))
    assert re.fullmatch(r'[a-zA-Z0-9._-]{1,64}', game['release_id'])
    manifest['game_release_id'] = game['release_id']
    stamped = None
    endgame_config = None
    for role in ['client', 'server']:
        base = ROOT / 'release/payload' / role
        data = {}
        for p in sorted(base.rglob('*')):
            if not p.is_file():
                continue
            rel = p.relative_to(base).as_posix()
            assert PurePosixPath(rel).parts[0] in ALLOWED and '..' not in PurePosixPath(rel).parts
            assert not p.is_symlink()
            raw = p.read_bytes()
            if rel == ADDON:
                assert digest(raw) == game['addon_sha256'], 'Game code changed: update game-version.json to a new compatibility ID after verification'
                raw = stamp(raw, game['release_id'])
                if stamped is None:
                    stamped = raw
                assert stamped == raw, 'Client/server game code or compatibility ID differs'
            if rel.endswith('.json'):
                json.loads(raw.decode('utf-8-sig'))
            if rel.endswith(('.zip', '.jar')):
                with zipfile.ZipFile(io.BytesIO(raw)) as nested:
                    assert nested.testzip() is None, rel
            data[rel] = raw
        assert ADDON in data and len(data) >= 20
        challenge_raw = data['config/cte2_endgame.json']
        challenge = json.loads(challenge_raw.decode('utf-8-sig'))
        assert 1 <= challenge['maxSessions'] <= 30 and challenge['raidRevives'] >= 0
        assert challenge['requirePinnacle'] and challenge['minLevel'] == 100
        if endgame_config is None:
            endgame_config = challenge_raw
        assert endgame_config == challenge_raw, 'Client/server endgame defaults differ'
        with zipfile.ZipFile(io.BytesIO(data[ADDON])) as core:
            assert 'kr/cte2/multi/endgame/Challenges.class' in core.namelist()
            assert 'kr/cte2/multi/endgame/ChallengeMaps.class' in core.namelist()
            assert 'kr/cte2/multi/mixin/ChallengeReturnPearlMixin.class' in core.namelist()
            assert 'kr/cte2/multi/client/ChallengeHud.class' in core.namelist()
            assert 'kr/cte2/multi/mixin/ChallengeMapDeviceMixin.class' in core.namelist()
            assert 'kr/cte2/multi/mixin/ChallengeMapActionsMixin.class' in core.namelist()
            assert core.read('assets/cte2_multiplayer/textures/item/ascended_map_upgrade.png').startswith(b'\x89PNG\r\n\x1a\n')
            assert 'assets/cte2_multiplayer/models/item/ascended_map_upgrade.json' in core.namelist()
            assert sum(n.startswith('assets/cte2_multiplayer/models/item/challenge_map_') for n in core.namelist()) == 7
            dimension = json.loads(core.read('data/cte2_multiplayer/dimension/endgame.json'))
            assert dimension['generator']['type'] == 'minecraft:flat' and dimension['generator']['settings']['layers'] == []
            assert not any('smoke' in n.lower() for n in core.namelist()), 'Test server code must not be distributed'
        if role == 'client':
            convenience = ['CTE2-StepUp-Compat-1.20.1-1.0.0.jar', 'stepitup-2.0.1-1.20.1-forge.jar', 'smartsprint-forge-1.20.1.jar', 'caramelChat-mc1.20.1-forge-1.2.2.jar', 'fullbright-1.0.0.jar']
            assert all('mods/' + n in data for n in convenience), 'Required convenience mod missing'
            assert not any('autofish' in n.lower() for n in data), 'Auto fishing must not be distributed'
            assert data['config/smartsprint.json'] and data['config/stepitup.json5']
        config = data['defaultconfigs/mine_and_slash-server.toml'].decode('utf-8-sig')
        assert re.search(r'^\s*MAP_START_COOLDOWN_SECONDS\s*=\s*10\s*$', config, re.M)
        name = 'patch-' + role + '.zip'
        with zipfile.ZipFile(output / name, 'w', zipfile.ZIP_DEFLATED) as archive:
            for rel, raw in data.items():
                archive.writestr(rel, raw)
        raw = (output / name).read_bytes()
        manifest['packages'][role] = {'url': f'{REPO}/releases/download/{tag}/{name}',
                                      'sha256': digest(raw), 'bytes': len(raw),
                                      'files': [{'path': n, 'bytes': len(b), 'sha256': digest(b)} for n, b in data.items()]}
    (output / 'update.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    print('PASS release packages, player release ID, original class bytes, archive CRC and 10-second map default:', release_id)


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('--release-id', required=True)
    args.add_argument('--tag', required=True)
    values = args.parse_args()
    build(values.release_id, values.tag)
