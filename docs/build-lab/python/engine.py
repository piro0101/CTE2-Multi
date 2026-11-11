"""Transparent, bounded 20 Hz build comparison model; not a Minecraft runtime."""
import copy, heapq, math
from collections import defaultdict
from catalog import get_catalog

ELEMENTS=['physical','fire','water','lightning','chaos']
def clamp(v,lo,hi):return max(lo,min(hi,v))
def num(v,default=0):
    try:
        value=float(v)
        return value if math.isfinite(value) else default
    except (ValueError,TypeError):return default
def interpolate(d,rank,maximum):return num(d.get('min'))+(num(d.get('max'))-num(d.get('min')))*rank/max(1,maximum)

def source(kind,key,level=100,roll=100,**extra):
    c=get_catalog();d=c.db.get(kind,{}).get(key,{})
    stats=d.get('stats',d.get('unique_stats',d.get('base_stats',[])))
    return {'kind':kind,'id':key,'name':c.name(kind,key),'level':level,'roll':roll,
            'enabled':True,'stats':[c.exact(s,roll,level) for s in stats],**extra}

def new_build(name='새 빌드',level=98):
    return {'version':1,'name':name,'level':level,'classes':['hunter','rogue'],'sources':[],
            'skills':[{'id':'meteor_arrow','rank':20,'enabled':True,'supports':[],'hits':1,'delay':0.6},
                      {'id':'explosive_arrow','rank':20,'enabled':True,'supports':[],'hits':1,'delay':0.2}],
            'core':{'strength':0,'dexterity':0,'intelligence':0},'overrides':{},'more_overrides':{},
            'snapshot':{},'origin':None,'notes':'','mode':'rebuild'}

def collect_rows(build,skill=None):
    c=get_catalog();level=int(clamp(num(build.get('level'),98),1,100));rows=[]
    for x in c.db['base'].get('original_mode_player',{}).get('base_stats',[]):rows.append(c.exact(x,100,level))
    for ele in ['fire','water','lightning','chaos']:
        rows.append({'stat':ele+'_resist','type':'FLAT','value':50 if level<25 else 25 if level<50 else 0 if level<75 else -25})
    for stat,value in build.get('core',{}).items():rows.append({'stat':stat,'type':'FLAT','value':num(value)})
    for src in build.get('sources',[]):
        if src.get('enabled',True):rows.extend(src.get('stats',[]))
    if skill:
        definition=c.db['skills'].get(skill['id'],{})
        maximum=definition.get('max_lvl',20)+c.balance.get('MAX_BONUS_SPELL_LEVELS',8)
        for st in definition.get('statsForSkillGem',[]):
            row=c.exact(st,100*num(skill.get('rank'),1)/maximum,level);rows.append(row)
        for gem in skill.get('supports',[]):
            if gem.get('enabled',True):rows.extend(source('supports',gem['id'],level,num(gem.get('roll'),100))['stats'])
    return rows

def calculate_stats(build,skill=None):
    c=get_catalog();rows=collect_rows(build,skill);bucket=defaultdict(lambda:{'FLAT':0.,'PERCENT':0.,'MORE':1.})
    def add(row,multi=1):
        sid=row.get('stat','');typ=row.get('type','FLAT').upper();value=num(row.get('value'))*multi
        if not sid:return
        if typ=='MORE':bucket[sid]['MORE']*=max(0,1+value/100)
        elif typ in ('FLAT','PERCENT'):bucket[sid][typ]+=value
    for row in rows:add(row)
    def resolve():
        values={};more={}
        for sid,b in bucket.items():
            meta=c.meta.get(sid,{})
            v=(meta.get('base',0)+b['FLAT'])*(1+b['PERCENT']/100)
            multiplicative_damage=meta.get('multiUseType')=='MULTIPLICATIVE_DAMAGE'
            # Native InCalcStatData applies MORE to ordinary stats, even percentage stats.
            # Only MULTIPLICATIVE_DAMAGE keeps a separate multiplier for the damage event.
            values[sid]=v if multiplicative_damage else v*b['MORE']
            values[sid]=clamp(values[sid],meta.get('min',-1e12),meta.get('max',1e12))
            more[sid]=b['MORE'] if multiplicative_damage else 1.
        return values,more
    values,more=resolve()
    allattr=values.get('all_attributes',0)
    for sid in ['strength','dexterity','intelligence']:
        bucket[sid]['FLAT']+=allattr
    values,more=resolve()
    for sid in ['strength','dexterity','intelligence']:
        for row in c.meta.get(sid,{}).get('core_stat_data',{}).get('stats',[]):add(c.exact(row,100,1),int(values.get(sid,0)))
    values,more=resolve()
    # Conversions at equal priority share a snapshot; newly obtained values are not re-used in that group.
    conversions=[]
    for sid,meta in c.meta.items():
        if 'add_to' in meta and 'adder_stat' in meta and values.get(sid,0):conversions.append((int(meta.get('priority',25)),sid,meta))
    for priority in sorted({x[0] for x in conversions}):
        snapshot=dict(values)
        for _,sid,meta in [x for x in conversions if x[0]==priority]:
            target=meta['add_to'];added=snapshot.get(meta['adder_stat'],0)*snapshot.get(sid,0)/100
            values[target]=values.get(target,0)+added
    # Snapshot mode is for manual/final-stat studies. It does not pretend to recalculate equipment changes.
    if build.get('mode')=='snapshot' and build.get('snapshot'):
        values={k:num(v.get('value')) for k,v in build['snapshot'].items()}
        more={k:num(v.get('more'),1) for k,v in build['snapshot'].items()}
    for sid,v in build.get('overrides',{}).items():values[sid]=num(v)
    for sid,v in build.get('more_overrides',{}).items():more[sid]=max(0,num(v,1))
    for resource in ['health','mana','energy','magic_shield']:
        values[resource]=max(0,values.get(resource,0))
    # Gear changes use this reconstructed result; the imported cache is only a separate reference.
    return values,more

def damage_parts(definition):
    result=[]
    def walk(value,path=''):
        if isinstance(value,dict):
            if value.get('type')=='damage':
                info=value.get('map',{});result.append({'element':info.get('element','Physical').lower(),'calc':info.get('value_calculation',''),'path':path})
            for k,v in value.items():walk(v,path+'/'+k)
        elif isinstance(value,list):
            for i,v in enumerate(value):walk(v,path+f'/{i}')
    walk(definition.get('attached',{}))
    return result

def spell_model(build,row,scenario):
    c=get_catalog();d=c.db['skills'].get(row.get('id'),{});conf=d.get('config',{});tags=conf.get('tags',{}).get('tags',[])
    v,m=calculate_stats(build,row);rank=clamp(num(row.get('rank'),1),1,100);maximum=d.get('max_lvl',20)+c.balance.get('MAX_BONUS_SPELL_LEVELS',8)
    percent=clamp(v.get('skill_speed',0),-75,300)
    attack='weapon_skill' in tags or 'ranged' in tags or 'melee' in tags
    if attack:percent+=clamp(v.get('attack_cast_speed',0),-75,300)
    if 'magic' in tags:percent+=clamp(v.get('cast_speed',0),-75,300)
    for tag in tags:percent+=clamp(v.get(tag+'_cast_time',0),-75,300)
    if 'not_affected_by_cast_speed' in tags:percent=0
    speed=1+max(-99,percent)/100
    recovery=max(c.balance.get('GLOBAL_COOLDOWN_TICKS',2),conf.get('cast_speed_ticks',20)/speed)
    cast=conf.get('cast_time_ticks',0)/speed
    cd_multi=max(c.balance.get('MIN_SPELL_COOLDOWN_MULTI',.2),1-clamp(v.get('cdr',0),0,75)/100-sum(clamp(v.get(tag+'_cdr',0),0,50)/100 for tag in tags))
    cooldown=max(0,int(conf.get('cooldown_ticks',0)*cd_multi))
    charge_cd=max(1,int(conf.get('charge_regen',0)*cd_multi))
    mana_multi=1.
    for gem in row.get('supports',[]):
        if gem.get('enabled',True):mana_multi*=num(c.db['supports'].get(gem['id'],{}).get('manaMulti'),1)
    level=num(build.get('level'),98);sc=c.balance.get('MANA_COST_SCALING',{});scaling=sc.get('base_scaling',1)+max(0,level-1)*sc.get('per_level_scaling',.2)
    costs={r:max(0,interpolate(conf.get(key,{}),rank,maximum)*scaling*mana_multi*(1+clamp(v.get(r+'_cost',0),-75,300)/100)) for r,key in [('mana','mana_cost'),('energy','ene_cost')]}
    parts=damage_parts(d);warnings=[];damage=0
    if row.get('manual_damage') is not None:
        damage=max(0,num(row['manual_damage']));warnings.append('실측 1회 피해 사용: 피해 증감·치명타·적 저항을 다시 적용하지 않습니다.')
    else:
        for part in parts:
            calc=c.db['values'].get(part['calc'])
            if not calc: warnings.append('미지원 피해 계산: '+part['calc']);continue
            base=int(interpolate(calc.get('base',{}),rank,maximum)*c.scale('weapon_damage',level))
            base+=sum(int(v.get(x.get('stat'),0)*interpolate(x.get('multi',{}),rank,maximum)) for x in calc.get('stat_scalings',[]))
            eff=interpolate(calc.get('dmg_effectiveness',{}).get('multi',{'min':1,'max':1}),rank,maximum)
            converted={e:max(0,v.get('flat_'+e+'_added_damage',0))*eff for e in ELEMENTS}
            converted[part['element']]=converted.get(part['element'],0)+base
            physical=max(0,converted['physical']);converted['physical']=0
            total_conv=sum(max(0,v.get('phys_to_'+e,0)) for e in ELEMENTS[1:]);denom=max(100,total_conv)
            for e in ELEMENTS[1:]:converted[e]+=physical*max(0,v.get('phys_to_'+e,0))/denom
            converted['physical']+=physical*max(0,1-total_conv/100)
            for e,amount in converted.items():
                if not amount:continue
                percent_ids=['total_damage','spell_damage','all_'+e+'_damage',conf.get('style','dex')+'_dmg']
                if attack:percent_ids+=['attack_damage']
                if e!='physical':percent_ids+=['all_elemental_damage','elemental_attack_damage' if attack else 'elemental_spell_damage']
                percent_ids += [tag+'_spell_dmg' for tag in tags]
                if 'projectile' in tags:percent_ids+=['projectile_damage']
                if 'area' in tags:percent_ids+=['area_dmg']
                increased=sum(v.get(s,0) for s in percent_ids);mult=math.prod(m.get(s,1) for s in set(percent_ids))
                resist=num(scenario.get('resists',{}).get(e),0)-v.get(e+'_penetration',0)
                amount*=max(0,1+increased/100)*mult*(1-clamp(resist,-100,100)/100)
                crit=clamp(v.get('critical_hit',0),0,100)/100
                amount*=1+crit*max(0,v.get('critical_damage',25))/100
                damage+=amount
        if row.get('id') not in ('meteor_arrow','explosive_arrow'):
            warnings.append('일반 직접 피해 추정: 반복·소환·지속 피해·별도 발동은 자동 재현하지 않습니다.')
        if not parts:warnings.append('직접 피해 계산이 없는 스킬입니다. 실측 피해 입력으로 비교할 수 있습니다.')
        if conf.get('channel_skill'):warnings.append('채널링은 펄스·유지 비용을 직접 확인해야 합니다. 실측 입력을 권장합니다.')
        if any(v.get(k,0) for k in ['burn_chance','poison_chance','bleed_chance']):warnings.append('화상·중독·출혈 지속 피해는 합산하지 않습니다.')
        if any(k.startswith('proc_') and val for k,val in v.items()):warnings.append('장비의 추가 발동 피해는 자동 합산하지 않습니다.')
    # Hits is an explicit experimental assumption, never inferred from projectile count.
    damage*=clamp(num(row.get('hits'),1),0,100)*clamp(num(scenario.get('hit_chance'),100),0,100)/100
    return {'id':row.get('id'),'name':c.name('skills',row.get('id','')),'interval_ticks':max(1,math.ceil(cast)+int(recovery)),
            'cast_ticks':math.ceil(cast),'recovery_ticks':int(recovery),'cooldown_ticks':cooldown,
            'charge_cd':charge_cd,'charges':int(conf.get('charges',0)), 'costs':costs,'damage':damage,
            'delay_ticks':int(clamp(num(row.get('delay'),0),0,30)*20),'stats':v,'more':m,'warnings':warnings,
            'parts':parts,'percent_speed':percent,'leech_hits':clamp(num(row.get('leech_hits'),1),0,100)*clamp(num(scenario.get('hit_chance'),100),0,100)/100}

def simulate(build,scenario):
    validate_build(build);seconds=clamp(num(scenario.get('duration'),60),1,600);ticks=int(seconds*20)
    models=[spell_model(build,r,scenario) for r in build.get('skills',[]) if r.get('enabled',True)]
    v,m=calculate_stats(build);resources={r:max(0,v.get(r,0)) for r in ['mana','energy']};pools={'mana':0.,'energy':0.}
    ready=[0]*len(models);charges=[s['charges'] for s in models];regen_at=[[] for s in models]
    result={s['id']:{'name':s['name'],'casts':0,'damage':0.,'mana_spent':0.,'energy_spent':0.,'interval':s['interval_ticks']/20,'damage_per_use':s['damage'],'warnings':s['warnings']} for s in models}
    events=[];series=[];total=0.;locked_until=0;waiting=0;first_starved=None;cursor=0;seq=0
    initial={r:resources[r]*clamp(num(scenario.get('start_'+r),100),0,100)/100 for r in resources};resources.update(initial)
    for tick in range(ticks+1):
        if tick and tick%20==0:
            for r in resources:
                cap=max(0,v.get(r,0));leech_cap=cap*clamp(v.get(r+'_leech_cap',5),0,10)/100
                leech=min(pools[r],leech_cap);pools[r]-=leech
                resources[r]=min(cap,resources[r]+max(0,v.get(r+'_regen',0))+leech)
        while events and events[0][0]<=tick:
            _,_,i=heapq.heappop(events);model=models[i];dmg=model['damage'];total+=dmg;result[model['id']]['damage']+=dmg
            if scenario.get('leech',True):
                for r in resources:
                    cap=max(0,v.get(r,0))*clamp(v.get(r+'_leech_cap',5),0,10)/100
                    pools[r]=min(cap*5,pools[r]+max(0,model['stats'].get(r+'_on_hit_hit',0))*model['leech_hits'])
        for i,model in enumerate(models):
            while regen_at[i] and regen_at[i][0]<=tick:
                heapq.heappop(regen_at[i]);charges[i]=min(model['charges'],charges[i]+1)
        if tick<ticks and tick>=locked_until:
            order=list(range(len(models)))
            if scenario.get('rotation','alternate')=='alternate' and models:order=order[cursor:]+order[:cursor]
            candidates=[i for i in order if tick>=ready[i] and (not models[i]['charges'] or charges[i]>0)]
            chosen=next((i for i in candidates if all(resources[r]+1e-8>=models[i]['costs'][r] for r in resources)),None)
            if chosen is not None:
                model=models[chosen];entry=result[model['id']];entry['casts']+=1
                for r in resources:resources[r]-=model['costs'][r];entry[r+'_spent']+=model['costs'][r]
                finish=tick+model['cast_ticks'];ready[chosen]=finish+model['cooldown_ticks'];locked_until=tick+model['interval_ticks']
                if model['charges']:
                    charges[chosen]-=1
                    last=max(regen_at[chosen]) if regen_at[chosen] else finish
                    heapq.heappush(regen_at[chosen],max(finish,last)+model['charge_cd'])
                heapq.heappush(events,(finish+model['delay_ticks'],seq,chosen));seq+=1;cursor=(chosen+1)%max(1,len(models))
            elif candidates:
                waiting+=1
                if first_starved is None:first_starved=tick/20
        if tick%20==0:series.append({'time':tick/20,'damage':round(total,3),'mana':round(resources['mana'],3),'energy':round(resources['energy'],3)})
    warnings=set()
    for model in models:warnings.update(model['warnings'])
    if build.get('mode')=='snapshot':warnings.add('저장 능력치 모드: 장비·특성·보조보석 변경을 재계산하지 않습니다. 능력치 직접 변경·실측 비교용입니다.')
    else:warnings.add('재구성 추정: 저장 능력치와 차이가 있을 수 있습니다. 조건부 버프·장비 제한·특수 발동·소환·지속 피해는 완전히 재현하지 않습니다.')
    warnings.add('적 명중률·저항·중첩 횟수는 입력 조건입니다. 실제 이동·충돌·방어력 곡선은 재현하지 않습니다.')
    if build.get('origin'):warnings.update(build.get('import_warnings',[]))
    ranged_weapon=any(s.get('enabled',True) and (s.get('gear_type') in ['bow','crossbow'] or s.get('id') in ['bow','crossbow'] or cgear(s).get('gear_slot') in ['bow','crossbow']) for s in build.get('sources',[]))
    if any('ranged' in get_catalog().db['skills'].get(s.get('id'),{}).get('config',{}).get('tags',{}).get('tags',[]) for s in build.get('skills',[]) if s.get('enabled',True)) and not ranged_weapon:
        warnings.add('활성 원거리 무기가 없습니다. 저장 시 다른 무기를 들었다면 장비 탭의 보관 장비에서 활·쇠뇌를 선택하고 기존 무기를 끄세요.')
    projected=max(0,v.get('health',0))+max(0,v.get('magic_shield',0))
    return {'duration':seconds,'total_damage':total,'dps':total/seconds,'casts':sum(x['casts'] for x in result.values()),
            'resource_wait_seconds':waiting/20,'first_starved':first_starved,'skills':list(result.values()),
            'series':series,'stats':v,'more':m,'warnings':sorted(warnings),'models':[{k:x[k] for k in ['id','name','costs','interval_ticks','cooldown_ticks','percent_speed','parts']} for x in models],
            'raw_survival_pool':projected,'pending_hits':len(events)}

def cgear(src):
    c=get_catalog()
    if src.get('kind')=='uniques':return c.db['gear'].get(c.db['uniques'].get(src.get('id'),{}).get('base_gear'),{})
    return c.db['gear'].get(src.get('id'),{})

def validate_build(build):
    if not isinstance(build,dict):raise ValueError('빌드 형식이 올바르지 않습니다.')
    if not 1<=num(build.get('level'),1)<=100:raise ValueError('캐릭터 레벨은 1~100입니다.')
    if len(build.get('sources',[]))>1000 or len(build.get('skills',[]))>16:raise ValueError('빌드 항목 수가 너무 많습니다.')
    ids=[]
    for row in build.get('skills',[]):
        if not isinstance(row,dict) or row.get('id') not in get_catalog().db['skills']:raise ValueError('설치된 게임에 없는 스킬입니다.')
        if row['id'] in ids:raise ValueError('같은 스킬을 두 번 등록할 수 없습니다.')
        ids.append(row['id'])
        if len(row.get('supports',[]))>5:raise ValueError('보조보석은 스킬당 최대 5개입니다.')
        gems=[g.get('id') for g in row.get('supports',[])]
        if len(gems)!=len(set(gems)):raise ValueError('같은 보조보석을 중복 장착할 수 없습니다.')
        for g in gems:
            if g not in get_catalog().db['supports']:raise ValueError('없는 보조보석입니다.')
    for src in build.get('sources',[]):
        if len(src.get('stats',[]))>100:raise ValueError('항목별 능력치가 너무 많습니다.')
        for row in src.get('stats',[]):
            if not math.isfinite(float(row.get('value',0))):raise ValueError('능력치는 유한한 숫자여야 합니다.')
