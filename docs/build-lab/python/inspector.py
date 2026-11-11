"""Native registry numbers for hover descriptions; no game-save mutation."""
import re
from catalog import get_catalog,clean
from engine import num,clamp,interpolate,damage_parts
from game import RARITIES,RARITY_KO,make_draft,build_equipment,stat_lines

def number(v):return f'{v:.2f}'.rstrip('0').rstrip('.')

def support_info(sid,rarity='mythic',roll=None,level=98):
    c=get_catalog();d=c.db['supports'].get(sid)
    if not d:raise ValueError('존재하지 않는 보조보석입니다.')
    if rarity not in RARITIES[:6]:raise ValueError('보조보석 등급을 선택하세요.')
    bounds=c.db['rarities'][rarity]['stat_percents']
    roll=bounds['max'] if roll is None else num(roll)
    if not bounds['min']<=roll<=bounds['max']:raise ValueError('보조보석 수치가 선택한 등급의 범위를 벗어났습니다.')
    rows=[c.exact(s,roll,int(clamp(num(level,98),1,100))) for s in d.get('stats',[])]
    return {'name':c.name('supports',sid),'rarity':rarity,'roll':roll,'range':bounds,'stats':rows,
        'lines':[f"{RARITY_KO[rarity]} · 옵션 수치 {number(roll)}% ({bounds['min']}~{bounds['max']}%)",*stat_lines(rows),
                 f"자원 소모 배율 ×{number(d.get('manaMulti',1))}"]}

def passive_info(build,sid,school=''):
    c=get_catalog();d=c.db['perks'].get(sid)
    if not d:raise ValueError('존재하지 않는 패시브입니다.')
    src=next((s for s in build.get('sources',[]) if s.get('id')==sid and s.get('school') and (not school or s['school']==school) and s.get('enabled',True)),{})
    rank=int(clamp(num(src.get('rank')),0,d.get('max_lvls',1)));level=int(clamp(num(build.get('level'),98),1,100))
    each=[c.exact(s,100,level) for s in d.get('stats',[])]
    def total(n):return [{**s,'value':s['value']*n} for s in each]
    rows=total(rank);lines=[f"현재 {rank}/{d.get('max_lvls',1)}레벨 · 합산 효과",*stat_lines(rows)]
    if rank<d.get('max_lvls',1):lines += [f'다음 {rank+1}레벨 · 합산 효과',*stat_lines(total(rank+1))]
    return {'name':c.name('perks',sid),'rank':rank,'stats':rows,'lines':lines}

def skill_info(build,sid):
    c=get_catalog();d=c.db['skills'].get(sid)
    if not d:raise ValueError('존재하지 않는 스킬입니다.')
    row=next((s for s in build.get('skills',[]) if s.get('id')==sid),{})
    learned=int(num(row.get('rank')));rank=max(1,learned);maximum=d.get('max_lvl',20)+c.balance.get('MAX_BONUS_SPELL_LEVELS',8)
    level=int(clamp(num(build.get('level'),98),1,100));conf=d.get('config',{})
    formulas={};calculations=[]
    def formula(key):
        calc=c.db['values'].get(key)
        if not calc:return '별도 효과'
        stype=calc.get('base_scaling_type','NORMAL');scale=c.balance.get(stype+'_STAT_SCALING',{})
        multi=scale.get('base_scaling',1)+max(0,level-1)*scale.get('per_level_scaling',0) if stype!='NONE' else 1
        base=int(interpolate(calc.get('base',{}),rank,maximum)*multi)
        parts=[f'기본 {number(base)}'] if base else []
        scalings=[]
        for target,field in [(False,'stat_scalings'),(True,'target_stat_scalings')]:
            for s in calc.get(field,[]):
                value=interpolate(s.get('multi',{}),rank,maximum)*100;label=('대상 ' if target else '')+c.name('stats',s.get('stat',''))
                parts.append(f'{label} × {number(value)}%');scalings.append({'stat':s.get('stat'),'percent':value,'target':target})
        return {'text':' + '.join(parts) or '0','base':base,'scalings':scalings,'effectiveness':interpolate(calc.get('dmg_effectiveness',{}).get('multi',{'min':1,'max':1}),rank,maximum)*100,'cap':calc.get('cap_to_wep_dmg',1000)}
    # Resolve all inline native calculations, including healing and secondary effects.
    description=clean(c.lang.get('spell.desc.'+sid,''))
    for key in dict.fromkeys(re.findall(r'\[calc:([^]]+)\]',description)+[p['calc'] for p in damage_parts(d)]):
        f=formula(key)
        if isinstance(f,dict):formulas[key]=f
    description=re.sub(r'\[calc:([^]]+)\]',lambda m:'('+formulas.get(m[1],{}).get('text','별도 효과')+')',description)
    lines=[f"현재 스킬 {learned}레벨" if learned else '미습득 · 1레벨 미리보기',f'캐릭터 Lv. {level} 기준',description]
    elements={'physical':'물리','fire':'화염','water':'냉기','lightning':'번개','chaos':'혼돈'}
    seen=set()
    for p in damage_parts(d):
        f=formulas.get(p['calc']);pair=(p['calc'],p['element'])
        if not f or pair in seen:continue
        seen.add(pair);label='운석 적중' if '/meteor/' in p['path'] else '화살 적중' if '/arrow/' in p['path'] else '피해'
        lines += [f"{label} · {elements.get(p['element'],p['element'])}",f['text'],f"추가 피해 효율 {number(f['effectiveness'])}%"]
        if f['cap']<50:lines.append('다른 능력치의 기여 상한: 무기 피해 기여량의 '+number(f['cap']*100)+'%')
        calculations.append({'element':p['element'],'label':label,**f})
    for key,f in formulas.items():
        if not any(p['calc']==key for p in damage_parts(d)):lines += [f['text']]
    stats=[c.exact(s,int(100*rank/maximum),level) for s in d.get('statsForSkillGem',[])]
    if stats:lines += ['이 레벨에서 얻는 스킬 효과',*stat_lines(stats)]
    cost=c.balance.get('MANA_COST_SCALING',{});cost_multi=cost.get('base_scaling',1)+max(0,level-1)*cost.get('per_level_scaling',.2)
    lines += [f"기본 마나 {number(interpolate(conf.get('mana_cost',{}),rank,maximum)*cost_multi)} · 기력 {number(interpolate(conf.get('ene_cost',{}),rank,maximum)*cost_multi)}",
              '기본 자원 소모는 보조보석·소모량 보정 전입니다.']
    return {'name':c.name('skills',sid),'rank':learned,'preview_rank':rank,'calculations':calculations,'lines':[s for s in lines if s]}

def inspect(data):
    kind=data.get('kind');b=data.get('build') or {};sid=data.get('id','')
    if kind=='support':return support_info(sid,data.get('rarity','mythic'),data.get('roll'),b.get('level',98))
    if kind=='passive':return passive_info(b,sid,data.get('school',''))
    if kind=='skill':return skill_info(b,sid)
    if kind=='item':
        draft=data.get('draft') or make_draft(data.get('base'),data.get('item',''),data.get('unique',''),b.get('level',98),data.get('rarity','mythic'))
        src=build_equipment(draft,data.get('slot','mainhand'))
        return {'name':src['name'],'lines':[f"Lv. {src['level']} · {RARITY_KO[src['rarity']]} · 품질 {src['quality']}%",*src['lines'],
                *([] if data.get('draft') else ['기본·고유 옵션 미리보기 · 접사는 선택 후 추가합니다.'])]}
    raise ValueError('지원하지 않는 툴팁입니다.')
