"""Browser-only adapter. No server filesystem discovery, network writes, or shared user storage."""
import base64
import json
from urllib.parse import urlsplit, parse_qs
from engine import new_build, simulate, source
from game import game_catalog, tree_graph, options_for, make_draft, build_equipment, toggle_tree
from inspector import inspect
from importer import import_player, gear_source
from catalog import get_catalog
from build_storage import validate


def dispatch(request):
    path = urlsplit(request['path']).path
    query = parse_qs(urlsplit(request['path']).query)
    data = request.get('data') or {}
    if path == '/api/catalog':
        return get_catalog().public
    if path == '/api/game':
        return game_catalog()
    if path == '/api/new':
        return new_build()
    if path == '/api/characters':
        return []
    if path == '/api/tree':
        return tree_graph(query.get('tree', ['talents'])[0])
    if path == '/api/options':
        return options_for(query.get('base', [''])[0], query.get('level', [98])[0])
    if path == '/api/inspect':
        return inspect(data)
    if path == '/api/equipment/new':
        draft = make_draft(data.get('base'), data.get('item', ''), data.get('unique', ''), data.get('level', 98), data.get('rarity', 'mythic'))
        return {'draft': draft, 'options': options_for(draft['base'], draft['level'])}
    if path == '/api/equipment':
        return build_equipment(data.get('draft', {}), data.get('slot', 'mainhand'))
    if path == '/api/tree-toggle':
        return {'sources': toggle_tree(data.get('build', {}), data.get('tree', 'talents'), data.get('key', ''), bool(data.get('free', False)))}
    if path == '/api/upload':
        raw = base64.b64decode(data.get('base64', ''), validate=True)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('저장 파일은 8MB 이하여야 합니다.')
        return import_player(raw, str(data.get('name', '선택한 파일'))[:200])
    if path == '/api/source':
        kind, key = data.get('kind'), data.get('id')
        if kind not in ['perks', 'gear', 'uniques', 'auras', 'affixes', 'supports'] or key not in get_catalog().db[kind]:
            raise ValueError('없는 카탈로그 항목입니다.')
        level = max(1, min(100, int(data.get('level', 98))))
        roll = max(0, min(100, float(data.get('roll', 100))))
        item = source(kind, key, level, roll)
        if kind == 'uniques':
            base = get_catalog().db['uniques'][key].get('base_gear', '')
            item = gear_source({'id': '', 'tag': {'mmorpg_gear': {'lvl': level, 'gtype': base, 'baseStats': {'p': 100}, 'uniqueStats': {'perc': [roll] * 20}, 'rar': 'unique'}, 'mmorpg_custom_data': {'data': {'map': {'uq': key}}}}}, base)
            item.update(kind='uniques', roll=roll)
        return item
    if path == '/api/simulate':
        result = {'a': simulate(data.get('a'), data.get('scenario', {}))}
        if data.get('b'):
            result['b'] = simulate(data['b'], data.get('scenario', {}))
        return result
    if path == '/api/builds' and request.get('data') is not None:
        return validate(data)
    raise ValueError('공개 웹판에서 지원하지 않는 요청입니다.')
