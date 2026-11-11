"""Bounded NBT decoder and explicit read-only player import."""
import copy, gzip, io, json, struct
from pathlib import Path
from catalog import ROOT, get_catalog
from engine import new_build, source

MAX_NBT=64*1024*1024
def read_nbt(raw):
    if raw[:2]==b'\x1f\x8b':raw=gzip.GzipFile(fileobj=io.BytesIO(raw)).read(MAX_NBT+1)
    if len(raw)>MAX_NBT:raise ValueError('저장 파일이 너무 큽니다.')
    stream=io.BytesIO(raw)
    def take(n):
        if n<0 or n>MAX_NBT:raise ValueError('잘못된 NBT 길이입니다.')
        data=stream.read(n)
        if len(data)!=n:raise ValueError('저장 파일이 잘렸습니다.')
        return data
    def number(fmt):return struct.unpack('>'+fmt,take(struct.calcsize('>'+fmt)))[0]
    def string():return take(number('H')).decode('utf-8',errors='replace')
    def payload(kind,depth=0):
        if depth>100:raise ValueError('저장 파일의 중첩이 너무 깊습니다.')
        if kind in range(1,7):return number({1:'b',2:'h',3:'i',4:'q',5:'f',6:'d'}[kind])
        if kind==7:return list(take(number('i')))
        if kind==8:return string()
        if kind==9:
            child,count=number('B'),number('i')
            if not 0<=count<=1000000:raise ValueError('잘못된 NBT 목록입니다.')
            return [payload(child,depth+1) for _ in range(count)]
        if kind==10:
            result={}
            while True:
                child=number('B')
                if child==0:return result
                key=string();result[key]=payload(child,depth+1)
        if kind in (11,12):
            count=number('i')
            if not 0<=count<=1000000:raise ValueError('잘못된 NBT 배열입니다.')
            return [number('i' if kind==11 else 'q') for _ in range(count)]
        raise ValueError('지원하지 않는 NBT 형식입니다.')
    kind=number('B');string()
    if kind!=10:raise ValueError('NBT 루트 형식이 올바르지 않습니다.')
    return expand(payload(kind))

def expand(x):
    if isinstance(x,dict):return {k:expand(v) for k,v in x.items()}
    if isinstance(x,list):return [expand(v) for v in x]
    if isinstance(x,str) and x.startswith(('{','[')):
        try:return expand(json.loads(x))
        except ValueError:pass
    return x

def gear_source(stack,slot):
    c=get_catalog();tag=stack.get('tag',{});gear=tag.get('mmorpg_gear',{});custom=tag.get('mmorpg_custom_data',{}).get('data',{}).get('map',{})
    level=gear.get('lvl',1);gtype=gear.get('gtype','');unique=custom.get('uq','');quality=min(100,max(0,int(custom.get('ql',0))))
    d=c.db['gear'].get(gtype,{});stats=[];parts=[];warnings=[]
    def add_parts(kind,key,roll):
        obj=c.db.get(kind,{}).get(key)
        if not obj and kind=='implicits':obj=c.db['affixes'].get(key)
        if not obj:
            if key:warnings.append('해석되지 않은 '+kind+': '+key)
            return
        st=obj.get('stats',obj.get('unique_stats',[]));parts.append({'kind':kind,'id':key,'roll':roll})
        stats.extend(c.exact(x,roll,level) for x in st)
    for affixes in gear.get('affixes',{}).values():
        if isinstance(affixes,list):
            for a in affixes:add_parts('affixes',a.get('id',''),a.get('p',100))
    imp=gear.get('imp',{});add_parts('implicits',imp.get('imp',''),imp.get('p',100))
    if unique:
        u=c.db['uniques'].get(unique)
        if u:
            rolls=gear.get('uniqueStats',{}).get('perc',[100]*20)
            for i,s in enumerate(u.get('unique_stats',[])):stats.append(c.exact(s,rolls[i] if i<len(rolls) else 100,level))
        else:warnings.append('해석되지 않은 유니크: '+unique)
    sockets=gear.get('sockets',{})
    for sock in sockets.get('so',[]):
        gem=c.db['gems'].get(sock.get('g'))
        if gem:
            key='on_weapons_stats' if 'weapon_family' in d.get('tags',{}).get('tags',[]) else 'on_jewelry_stats' if gtype in ['ring','necklace'] else 'on_armor_stats'
            stats.extend(c.exact(s,sock.get('p',100),level) for s in gem.get(key,[]))
        else:warnings.append('룬/소켓 효과 미해석: '+str(sock.get('g')))
    if sockets.get('rw'):warnings.append('룬워드 조건부/소켓 개별 효과 확인 필요: '+sockets['rw'])
    ench=gear.get('ench') or {}
    if ench.get('en'):
        aff=c.db['affixes'].get(ench['en'])
        if aff:
            percent=c.db.get('rarities',{}).get(ench.get('rar','common'),{}).get('stat_percents',{}).get('max',100)
            stats.extend(c.exact(s,percent,level) for s in aff.get('stats',[]))
    if tag.get('Enchantments'):warnings.append('일부 인챈트 효과는 장비 재구성 합계에서 제외됩니다.')
    # Local gear affixes modify only this item's base values.
    base=[]
    base_roll=gear.get('baseStats',{}).get('p',100)+quality
    for s in d.get('base_stats',[]):
        row=c.exact(s,base_roll,level);sid=row['stat'];local='gear_weapon_damage' if sid=='weapon_damage' else 'gear_defense' if sid in ['armor','dodge','magic_shield'] else None
        if local:
            row['value']+=sum(x['value'] for x in stats if x['stat']==local and x['type']=='FLAT')
            for x in stats:
                if x['stat']==local and x['type']=='PERCENT':row['value']*=1+x['value']/100
        base.append(row)
    stats=[x for x in stats if x['stat'] not in ['gear_defense','gear_weapon_damage']]+base
    from game import draft_from_stack,stat_lines
    return {'kind':'equipment','id':unique or gtype,'name':c.name('uniques',unique) if unique else c.name('gear',gtype),
            'slot':slot,'gear_type':gtype,'level':level,'roll':gear.get('baseStats',{}).get('p',100),'quality':quality,
            'rarity':gear.get('rar',''),'sockets':sockets.get('sl',0),'enabled':True,'stats':stats,'parts':parts,
            'warnings':sorted(set(warnings)),'item_id':stack.get('id',''),'editor':draft_from_stack(stack),
            'icon':'/api/icon?item='+stack.get('id',''),'lines':stat_lines(stats)}

def import_player(raw,origin='선택한 저장 파일'):
    c=get_catalog();root=read_nbt(raw);player=root.get('Data',{}).get('Player',root)
    caps=player.get('ForgeCaps',{});pd=caps.get('mmorpg:player_data');entity=caps.get('mmorpg:entity_data',{})
    if not pd:raise ValueError('Mine and Slash 캐릭터 정보가 없습니다. level.dat 또는 플레이어 .dat 파일을 선택하세요.')
    b=new_build('불러온 캐릭터',entity.get('level',1));b['origin']=origin
    b['classes']=pd.get('asc',{}).get('school_order',[]);b['core']=pd.get('stats',{}).get('map',{})
    b['point_budgets']={}
    for category,rule in c.balance.get('player_points',{}).items():
        saved=pd.get('points',{}).get('map',{}).get(category,{})
        points=rule.get('base_points',0)+b['level']*rule.get('points_per_lvl',0)+saved.get('bonus_points',0)+saved.get('cheat_points',0)
        b['point_budgets'][category]=int(min(rule.get('max_total_points',points),points))
    b['sources']=[];b['skills']=[];b['inventory_gear']=[];warnings=[]
    selected=player.get('SelectedItemSlot',0)
    for stack in player.get('Inventory',[]):
        slot=stack.get('Slot');slot=slot+256 if isinstance(slot,int) and slot<0 else slot
        if slot in [selected,100,101,102,103,150] and stack.get('tag',{}).get('mmorpg_gear'):
            names={selected:'주무기',100:'신발',101:'바지',102:'상의',103:'머리',150:'보조무기'}
            b['sources'].append(gear_source(stack,names.get(slot,str(slot))))
        elif stack.get('tag',{}).get('mmorpg_gear'):
            b['inventory_gear'].append(gear_source(stack,'보관 장비'))
    for group in caps.get('curios:inventory',{}).get('Curios',[]):
        for stack in group.get('StacksHandler',{}).get('Stacks',{}).get('Items',[]):
            if stack.get('tag',{}).get('mmorpg_gear'):b['sources'].append(gear_source(stack,group.get('Identifier','장신구')))
            if stack.get('tag',{}).get('mmorpg_omen'):
                b['sources'].append({'kind':'codex','id':stack.get('id',''),'name':'장착 코덱스','enabled':True,'stats':[],
                    'raw':stack['tag']['mmorpg_omen'],'warnings':['코덱스 효과는 재구성 합계에서 제외됩니다. 저장 능력치 또는 직접 추가를 이용하세요.']})
                warnings.append('코덱스 원본은 보존했으며 효과 합산은 별도 확인이 필요합니다.')
    for category,tree_id in [('TALENTS','talents'),('ASCENDANCY','ascendancy')]:
        for coord in pd.get('tals',{}).get('perks',{}).get(category,{}).get('list',[]):
            key=c.grid.get(tree_id,{}).get((coord.get('x'),coord.get('y')))
            if key:b['sources'].append(source('perks',key,b['level'],100,tree=category,coord=coord))
            else:warnings.append('해석되지 않은 특성 좌표: '+str(coord))
    allocated=pd.get('asc',{}).get('allocated_lvls',{})
    for sid,rank in allocated.items():
        if sid in c.db['perks'] and sid not in c.db['skills']:
            s=source('perks',sid,b['level']);s['stats']=[{**r,'value':r['value']*rank} for r in s['stats']];s['rank']=rank
            s['school']=next((k for k in b['classes'] if sid in c.db.get('schools',{}).get(k,{}).get('perks',{})),'')
            b['sources'].append(s)
    gems={x.get('Slot'):x.get('tag',{}).get('mmorpg_skill_gem',{}) for x in pd.get('gems',[])}
    hotbar=pd.get('casting',{}).get('hotbar',{})
    for spell in pd.get('casting',{}).get('spells',[]):
        sid=spell.get('id');hotkey=next((int(k) for k,v in hotbar.items() if v==sid),None)
        supports=[]
        if hotkey is not None:
            for s in range(5):
                gem=gems.get(hotkey*6+s+1,{})
                if gem.get('id') in c.db['supports']:supports.append({'id':gem['id'],'roll':gem.get('perc',100),'enabled':True,'rarity':gem.get('rar','')})
        if sid in c.db['skills']:
            b['skills'].append({'id':sid,'name':c.name('skills',sid),'rank':spell.get('rank',1),'base_rank':spell.get('rankBeforePlusSkills',spell.get('rank',1)),'bonus_rank':spell.get('bonus_ranks',0),'enabled':sid in ['meteor_arrow','explosive_arrow'],
                                'supports':supports,'hits':1,'delay':.6 if sid=='meteor_arrow' else .2})
    if not any(s['enabled'] for s in b['skills']):
        for s in b['skills'][:1]:s['enabled']=True
    for stack in pd.get('auras',[]):
        gem=stack.get('tag',{}).get('mmorpg_skill_gem',{})
        if gem.get('id') in c.db['auras']:b['sources'].append(source('auras',gem['id'],b['level'],gem.get('perc',100)))
    for stack in pd.get('jewels',[]):
        j=stack.get('tag',{}).get('mmorpg_jewel',{});stats=[]
        for a in j.get('affixes',[])+j.get('cor',[]):stats.extend(source('affixes',a.get('id',''),j.get('lvl',b['level']),a.get('p',100))['stats'])
        b['sources'].append({'kind':'jewel','id':stack.get('id',''),'name':'장착 주얼 '+str(stack.get('Slot',0)+1),'enabled':True,'stats':stats,'level':j.get('lvl',b['level'])})
    cache=entity.get('mmorpg_unit',{})
    if isinstance(cache,dict):
        for row in cache.values():
            if isinstance(row,dict) and row.get('i'):b['snapshot'][row['i']]={'value':row.get('v',0),'more':row.get('m',1)}
    warnings.extend(['저장 능력치는 마지막 계산 당시의 버프·스킬 보조 효과를 포함할 수 있습니다.',
                     '기본 모드는 장비·특성을 재구성한 추정치입니다. 저장 능력치는 별도 참고 탭에서 확인하세요.',
                     '특성 경로·장비 착용 조건·오라 수용량의 합법성 검증은 첫 버전에서 자동 수행하지 않습니다.'])
    for src in b['sources']:warnings.extend(src.get('warnings',[]))
    b['import_warnings']=sorted(set(warnings));b['raw_summary']={'talents':len(pd.get('tals',{}).get('perks',{}).get('TALENTS',{}).get('list',[])),
        'ascendancy':len(pd.get('tals',{}).get('perks',{}).get('ASCENDANCY',{}).get('list',[])),
        'supports':sum(len(s['supports']) for s in b['skills']),'snapshot_stats':len(b['snapshot'])}
    return b
