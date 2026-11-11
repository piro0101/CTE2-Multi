"""Game-style, item-bound equipment editing and native talent grid topology."""
import copy,csv,functools,re
from collections import deque
from catalog import get_catalog,clean
from engine import source,num,clamp

RARITIES=['common','uncommon','rare','epic','legendary','mythic','unique','runeword']
RARITY_KO=dict(zip(RARITIES,['일반','고급','희귀','영웅','전설','신화','유니크','룬워드']))
SLOTS=[('mainhand','주무기'),('offhand','보조 장비'),('helmet','머리'),('chest','상의'),('pants','바지'),('boots','신발'),('ring1','반지 1'),('ring2','반지 2'),('necklace','목걸이'),('elytra','겉날개')]
CLASS_KO={'hunter':'사냥꾼','rogue':'도적','warrior':'전사','mage':'마법사','shaman':'주술사','sanguimancer':'혈술사','elementalist':'원소술사','cleric':'성직자','minstrel':'음유시인','chronomancer':'시간술사','brawler':'무투가','summoner':'소환사','necromancer':'강령술사','paladin':'성기사','druid':'드루이드','warlock':'흑마법사','sorcerer':'마술사'}

def eligible(affix,base):
    tags=set(base.get('tags',{}).get('tags',[]))
    for r in affix.get('requirements',{}).get('tag_requirements',[]):
        inc,exc=set(r.get('included',[])),set(r.get('excluded',[]))
        if tags&exc:return False
        if inc and (r.get('req_type')=='HAS_ALL' and not inc<=tags or r.get('req_type')=='INCLUDES_ANY' and not tags&inc):return False
    return True

def icon_url(path):
    if not path:return ''
    ns,sep,p=path.partition(':')
    return '/assets/'+(ns+'/'+p if sep else 'mmorpg/'+path)

def stat_lines(rows):
    c=get_catalog();out=[]
    for r in rows:
        sid=r.get('stat','');v=num(r.get('value'));typ=r.get('type','FLAT').upper();name=c.name('stats',sid)
        value=f'{v:.2f}'.rstrip('0').rstrip('.')
        if '[VAL1]' in name:out.append(name.replace('[VAL1]',value));continue
        meta=c.meta.get(sid,{})
        perc=meta.get('is_perc',meta.get('perc',False)) or sid.startswith(('phys_to_','plus_phys_to_')) or any(s in sid for s in ['damage','_dmg','_speed','_chance','_cap','_resist','_penetration','_cast_time','_recovery','_cost'])
        if sid in ['weapon_damage','gear_weapon_damage','accuracy','armor_penetration','health','mana','energy','magic_shield','dodge','armor','strength','intelligence','dexterity'] or sid.startswith('flat_') or sid.startswith('plus_lvl_'):perc=False
        suffix='%' if typ in ['MORE','PERCENT'] or perc else ''
        tail=' 증폭' if typ=='MORE' else ' 증가' if typ=='PERCENT' else ''
        out.append(name+' '+('+' if v>=0 else '')+value+suffix+tail)
    return out

def draft_from_stack(stack):
    tag=stack.get('tag',{});g=tag.get('mmorpg_gear',{});custom=tag.get('mmorpg_custom_data',{}).get('data',{}).get('map',{})
    ench=g.get('ench',{}) or {}
    return {'base':g.get('gtype',''),'item':stack.get('id',''),'imported_item':stack.get('id',''),'unique':custom.get('uq',''),
            'rarity':g.get('rar','mythic'),'level':g.get('lvl',1),'quality':min(100,max(0,int(custom.get('ql',0)))),
            'base_roll':g.get('baseStats',{}).get('p',100),'prefixes':copy.deepcopy(g.get('affixes',{}).get('pre',[])),
            'suffixes':copy.deepcopy(g.get('affixes',{}).get('suf',[])),'corruption':copy.deepcopy(g.get('affixes',{}).get('cor',[])),
            'implicit':copy.deepcopy(g.get('imp',{})),'infusion':{'id':ench.get('en',''),'rarity':ench.get('rar','common')},
            'sockets':copy.deepcopy(g.get('sockets',{'sl':0,'so':[],'rw':'','rp':0})),
            'unique_rolls':g.get('uniqueStats',{}).get('perc',[100]*20),'raw_tag':copy.deepcopy(tag)}

def make_draft(base,item='',unique='',level=98,rarity='mythic'):
    c=get_catalog()
    if base not in c.db['gear']:raise ValueError('존재하지 않는 장비입니다.')
    if unique:
        if unique not in c.db['uniques'] or c.db['uniques'][unique].get('base_gear')!=base:raise ValueError('유니크와 기본 장비 유형이 일치하지 않습니다.')
        rarity='unique'
    if rarity not in RARITIES:raise ValueError('장비 등급을 선택하세요.')
    possible=c.db['gear'][base].get('possible_items',[])
    if not item:
        available=[x for x in possible if RARITIES.index(x.get('min_rar','common'))<=RARITIES.index(rarity)]
        item=(available[-1] if available else possible[0] if possible else {}).get('item_id','minecraft:air')
    return {'base':base,'item':item,'unique':unique,'rarity':rarity,'level':int(clamp(num(level,98),1,100)),
        'quality':0,'base_roll':100,'prefixes':[],'suffixes':[],'corruption':[],'implicit':{},'infusion':{'id':'','rarity':'mythic'},
        'sockets':{'sl':0,'so':[],'rw':'','rp':0},'unique_rolls':[100]*20}

def options_for(base,level=98):
    c=get_catalog();g=c.db['gear'].get(base)
    if not g:raise ValueError('장비를 먼저 선택하세요.')
    result={}
    for typ,key in [('prefix','prefixes'),('suffix','suffixes'),('chaos_stat','corruption'),('enchant','infusion'),('implicit','implicit')]:
        rows=[]
        for aid,a in c.db['affixes'].items():
            if a.get('type')!=typ or not eligible(a,g) or (typ!='implicit' and a.get('weight',0)<=0):continue
            rows.append({'id':aid,'name':clean(c.lang.get('mmorpg.affix.'+aid,'')) or ' / '.join(c.name('stats',s['stat']) for s in a.get('stats',[])),
                'stats':a.get('stats',[]),'lines':stat_lines([c.exact(s,100,int(clamp(num(level,98),1,100))) for s in a.get('stats',[])]),
                'group':a.get('one_of_a_kind',''),'only_one':a.get('only_one_per_item',True)})
        result[key]=sorted(rows,key=lambda a:a['name'])
    return result

def build_equipment(draft,slot='mainhand'):
    from importer import gear_source
    c=get_catalog();d=copy.deepcopy(draft);base=d.get('base');g=c.db['gear'].get(base)
    if not g:raise ValueError('장비를 먼저 선택하세요.')
    tags=set(g.get('tags',{}).get('tags',[]));native_slot=g.get('gear_slot')
    valid=(slot=='mainhand' and 'weapon_family' in tags or slot=='offhand' and ('offhand_family' in tags or 'weapon_family' in tags and 'two_handed' not in tags) or slot in ['ring1','ring2'] and native_slot=='ring' or slot==native_slot)
    if not valid:raise ValueError('해당 착용 칸에 넣을 수 없는 장비입니다.')
    rarity=d.get('rarity','mythic')
    if rarity not in RARITIES:raise ValueError('잘못된 장비 등급입니다.')
    unique=d.get('unique','')
    if unique and (unique not in c.db['uniques'] or c.db['uniques'][unique].get('base_gear')!=base or rarity!='unique'):raise ValueError('유니크 장비 구성이 올바르지 않습니다.')
    level=int(clamp(num(d.get('level'),98),1,100));quality=int(clamp(num(d.get('quality')),0,100))
    max_affixes=int(c.db['rarities'].get(rarity,{}).get('min_affixes',6))//2
    if unique:max_affixes=0
    for key,typ in [('prefixes','prefix'),('suffixes','suffix'),('corruption','chaos_stat')]:
        rows=d.get(key,[])
        if len(rows)>(2 if key=='corruption' else max_affixes):raise ValueError('이 장비의 '+{'prefixes':'접두사','suffixes':'접미사','corruption':'타락'}[key]+' 최대 개수를 초과했습니다.')
        ids=[]
        for row in rows:
            a=c.db['affixes'].get(row.get('id'),{})
            if a.get('type')!=typ or not eligible(a,g) or a.get('weight',0)<=0:raise ValueError('이 장비에 붙을 수 없는 옵션입니다.')
            if row['id'] in ids and a.get('only_one_per_item',True):raise ValueError('같은 옵션을 중복 선택할 수 없습니다.')
            ids.append(row['id']);ar=row.get('rar','mythic')
            if ar not in RARITIES[:6]:ar='mythic';row['rar']=ar
            bounds=c.db['rarities'].get(ar,{}).get('stat_percents',{'min':0,'max':100})
            if key!='corruption' and not bounds['min']<=num(row.get('p',100))<=bounds['max']:raise ValueError('선택한 옵션 등급의 수치 범위를 벗어났습니다.')
            row['ty']=typ
    groups=set()
    for row in d.get('prefixes',[])+d.get('suffixes',[]):
        group=c.db['affixes'][row['id']].get('one_of_a_kind','')
        if group and group in groups:raise ValueError('같은 계열의 접사를 함께 선택할 수 없습니다.')
        if group:groups.add(group)
    inf=d.get('infusion',{});inf_id=inf.get('id','')
    if inf_id:
        a=c.db['affixes'].get(inf_id,{})
        if a.get('type')!='enchant' or not eligible(a,g) or a.get('weight',0)<=0:raise ValueError('이 장비에는 해당 주입을 선택할 수 없습니다.')
        if inf.get('rarity') not in RARITIES[:6]:raise ValueError('주입 등급이 올바르지 않습니다.')
    imp=d.get('implicit',{});imp_id=imp.get('imp','')
    if imp_id:
        a=c.db['affixes'].get(imp_id,{})
        if a.get('type')!='implicit' or not eligible(a,g):raise ValueError('장비의 기본 옵션이 올바르지 않습니다.')
    allowed_items={x.get('item_id') for x in g.get('possible_items',[])}
    force_item=c.db['uniques'].get(unique,{}).get('force_item_id','') if unique else ''
    if d.get('item') not in allowed_items and d.get('item')!=force_item and d.get('item')!=d.get('imported_item'):raise ValueError('기본 장비와 아이템이 일치하지 않습니다.')
    gear={'gtype':base,'rar':rarity,'lvl':level,'baseStats':{'p':clamp(num(d.get('base_roll'),100),0,100)},
          'affixes':{'pre':d.get('prefixes',[]),'suf':d.get('suffixes',[]),'cor':d.get('corruption',[])},'imp':imp,
          'sockets':d.get('sockets',{'sl':0,'so':[],'rw':'','rp':0}),'uniqueStats':{'perc':d.get('unique_rolls',[100]*20)}}
    if inf_id:gear['ench']={'en':inf_id,'rar':inf['rarity']}
    d['quality']=quality;d['level']=level
    tag=copy.deepcopy(d.get('raw_tag',{}));tag['mmorpg_gear']=gear
    tag.setdefault('mmorpg_custom_data',{}).setdefault('data',{}).setdefault('map',{}).update({'ql':str(quality),'uq':unique})
    stack={'id':d['item'],'tag':tag,'Count':1}
    src=gear_source(stack,dict(SLOTS).get(slot,slot));src.update({'kind':'equipment','ui_slot':slot,'editor':d,'quality':quality,'rarity':rarity,
        'icon':'/api/icon?item='+d['item'],'lines':stat_lines(src['stats']),'tags':g.get('tags',{}).get('tags',[])})
    src['name']=c.name('uniques',unique) if unique else RARITY_KO[rarity]+' '+c.name('gear',base)
    return src

@functools.lru_cache(maxsize=3)
def tree_graph(tree):
    c=get_catalog()
    if tree not in ['talents','ascendancy']:raise ValueError('지원하지 않는 특성 트리입니다.')
    cells={(x,y):token.strip().lower() for y,row in enumerate(csv.reader(c.db['trees'][tree]['perks'].splitlines())) for x,token in enumerate(row)}
    nodes={xy:k for xy,k in cells.items() if k in c.db['perks']};edges=set()
    def token(xy):return cells.get(xy,'')
    def is_talent(xy):return len(token(xy))>2 and token(xy)!='[center]'
    for start in nodes:
        colors={token((start[0]+dx,start[1]+dy)) for dx in [-1,0,1] for dy in [-1,0,1] if len(token((start[0]+dx,start[1]+dy)))==1}
        for color in colors:
            q=deque([start]);seen=set()
            while q:
                xy=q.popleft()
                if xy in seen:continue
                seen.add(xy)
                if xy in nodes and xy!=start:
                    if abs(xy[0]-start[0])<12 and abs(xy[1]-start[1])<12:edges.add(tuple(sorted((start,xy))))
                    continue
                for dx in [-1,0,1]:
                    for dy in [-1,0,1]:
                        if dx==dy==0:continue
                        if dx and dy and (is_talent((xy[0]+dx,xy[1])) or is_talent((xy[0],xy[1]+dy))):continue
                        nxt=(xy[0]+dx,xy[1]+dy)
                        if is_talent(nxt) or token(nxt)==color:q.append(nxt)
    result=[]
    for (x,y),key in nodes.items():
        d=c.db['perks'][key];result.append({'x':x,'y':y,'key':f'{x},{y}','id':key,'name':c.name('perks',key),'icon':icon_url(d.get('icon','')),
            'entry':d.get('is_entry',False),'type':d.get('type','STAT'),'stats':d.get('stats',[]),
            'lines':stat_lines([c.exact(s,100,1) for s in d.get('stats',[])])})
    return {'nodes':result,'edges':[[f'{a[0]},{a[1]}',f'{b[0]},{b[1]}'] for a,b in sorted(edges)],'tree':tree}

def toggle_tree(build,tree,key,free=False):
    graph=tree_graph(tree);nodes={n['key']:n for n in graph['nodes']}
    if key not in nodes:raise ValueError('존재하지 않는 특성입니다.')
    category='TALENTS' if tree=='talents' else 'ASCENDANCY';sources=build.get('sources',[])
    selected={f"{s['coord']['x']},{s['coord']['y']}" for s in sources if s.get('tree')==category and s.get('coord') and s.get('enabled',True)}
    neighbors={k:set() for k in nodes}
    for a,b in graph['edges']:neighbors[a].add(b);neighbors[b].add(a)
    n=nodes[key];removing=key in selected;new=selected-{key} if removing else selected|{key}
    if not free:
        if not removing and selected and not neighbors[key]&selected:raise ValueError('이미 찍은 특성과 연결된 노드를 선택하세요.')
        if not removing and not selected and not n['entry']:raise ValueError('시작 노드부터 선택하세요.')
        budget=int(build.get('point_budgets',{}).get(category,200 if tree=='talents' else 10))
        if not removing and len(new)>budget:raise ValueError('사용 가능한 특성 포인트가 부족합니다.')
        if removing and new:
            reached={k for k in new if nodes.get(k,{}).get('entry')};q=deque(reached)
            while q:
                for k in neighbors[q.popleft()]&new:
                    if k not in reached:reached.add(k);q.append(k)
            if not new<=reached:raise ValueError('다른 특성의 연결이 끊어집니다. 끝 노드부터 되돌리세요.')
    result=copy.deepcopy(sources)
    if removing:result=[s for s in result if not (s.get('tree')==category and s.get('coord')=={'x':n['x'],'y':n['y']})]
    else:result.append(source('perks',n['id'],build.get('level',98),100,tree=category,coord={'x':n['x'],'y':n['y']}))
    return result

@functools.lru_cache(maxsize=1)
def game_catalog():
    c=get_catalog();out={'items':[],'schools':[],'slots':SLOTS,'rarities':{},'names':c.public['stat_names']}
    for key,d in c.db['rarities'].items():
        if key in RARITIES:out['rarities'][key]={'name':RARITY_KO[key],'range':d.get('stat_percents',{'min':0,'max':100}),'base_range':d.get('base_stat_percents',{'min':0,'max':100}),'affixes':d.get('min_affixes',6)//2}
    for base,g in c.db['gear'].items():
        if g.get('gear_slot') in ['head','elytra']:continue
        for obj in g.get('possible_items',[]):
            out['items'].append({'key':base+'|'+obj['item_id'],'base':base,'item':obj['item_id'],'unique':'','name':c.name('gear',base),
                'rarity':obj.get('min_rar','common'),'slot':g.get('gear_slot',''),'tags':g.get('tags',{}).get('tags',[]),'icon':'/api/icon?item='+obj['item_id']})
    for uid,u in c.db['uniques'].items():
        if u.get('weight',0)<=0:continue
        base=u.get('base_gear','');g=c.db['gear'].get(base)
        if not g:continue
        items=g.get('possible_items',[]);item=u.get('force_item_id') or (items[-1]['item_id'] if items else '')
        if item:out['items'].append({'key':'unique|'+uid,'base':base,'item':item,'unique':uid,'name':c.name('uniques',uid),'rarity':'unique','slot':g.get('gear_slot',''),'tags':g.get('tags',{}).get('tags',[]),'icon':'/api/icon?item='+item})
    for key,d in c.db['schools'].items():
        if key in ['mercenary','gear','mob','basic'] or not d.get('perks'):continue
        cells=[]
        for sid,xy in d['perks'].items():
            kind='skills' if sid in c.db['skills'] else 'perks';p=c.db[kind].get(sid)
            if not p:continue
            cells.append({'id':sid,'kind':kind,'x':xy['x'],'y':xy['y'],'name':c.name(kind,sid),'icon':icon_url(p.get('icon','mmorpg:textures/gui/spells/icons/'+sid+'.png')),
                'max':p.get('max_lvls',p.get('max_lvl',1)),'min':p.get('min_lvl',d.get('lvl_reqs',[1])[min(xy['y'],len(d.get('lvl_reqs',[1]))-1)]),
                'lines':([re.sub(r'\[calc:[^]]+\]', '(레벨에 따른 피해량)',clean(c.lang.get('spell.desc.'+sid,'')))] if kind=='skills' else stat_lines([c.exact(s,100,1) for s in p.get('stats',[])])),'tags':p.get('config',{}).get('tags',{}).get('tags',[])})
        out['schools'].append({'id':key,'name':{'crusader':'성전사','cryolancer':'빙결술사'}.get(key,CLASS_KO.get(key,key)),'cells':cells,'levels':d.get('lvl_reqs',[1,5,10,15,20,25,30])})
    out['supports']=[{**r,'lines':stat_lines([c.exact(s,100,98) for s in r.get('stats',[])]),'icon':'/api/icon?item=mmorpg:skill_gems/support/'+(r.get('style') or 'STR').lower()} for r in c.public['supports']]
    return out
