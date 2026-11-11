"""Read-only catalog of the installed CTE2 registries. No network dependencies."""
from pathlib import Path
import csv, hashlib, json, re, zipfile

APP = Path(__file__).resolve().parent
ROOT = APP.parent.parent
FOLDERS = {'skills':'mmorpg_spells','supports':'mmorpg_support_gem','auras':'mmorpg_aura',
           'perks':'mmorpg_perk','trees':'mmorpg_talent_tree','affixes':'mmorpg_affixes',
           'uniques':'mmorpg_unique_gears','gear':'mmorpg_base_gear_types','stats':'mmorpg_stat',
           'gems':'mmorpg_gems','implicits':'mmorpg_gear_implicit','values':'mmorpg_value_calc',
           'balance':'mmorpg_game_balance','base':'mmorpg_base_stats',
           'schools':'mmorpg_spell_school','rarities':'mmorpg_gear_rarity'}
NAMES = {'health':'최대 체력','mana':'최대 마나','energy':'최대 기력','magic_shield':'마법 보호막',
 'armor':'방어력','dodge':'회피 수치','health_regen':'초당 체력 재생','mana_regen':'초당 마나 재생',
 'energy_regen':'초당 기력 재생','magic_shield_regen':'초당 보호막 재생','strength':'힘','dexterity':'민첩',
 'intelligence':'지능','skill_speed':'스킬 속도','attack_cast_speed':'공격 스킬 속도','cast_speed':'마법 스킬 속도',
 'attack_speed':'공격 속도','faster_projectiles':'투사체 속도','critical_hit':'치명타 확률',
 'critical_damage':'치명타 추가 피해','weapon_damage':'무기 피해','fire_resist':'화염 저항',
 'water_resist':'냉기 저항','lightning_resist':'번개 저항','chaos_resist':'혼돈 저항',
 'cdr':'재사용 대기시간 감소','total_damage':'전체 피해','projectile_damage':'투사체 피해',
 'spell_damage':'스킬 피해','all_fire_damage':'화염 피해','physical_resist':'물리 저항',
 'flat_physical_added_damage':'추가 물리 피해','mana_on_hit_hit':'적중 시 마나 흡수',
 'energy_on_hit_hit':'적중 시 기력 흡수','weapon_skill_cast_time':'공격 태그 스킬 속도',
 'meteor_arrow':'메테오 화살','explosive_arrow':'폭발 화살','gear_defense':'장비 기본 방어 수치',
 'gear_weapon_damage':'장비 기본 무기 피해'}

def clean(text):
    return re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', re.sub(r'§.', '', str(text)))

class Catalog:
    def __init__(self):
        self.db = {k:{} for k in FOLDERS}
        self.lang = {}
        self.sources = []
        jar = next((ROOT/'mods').glob('Mine_and_Slash-*'))
        with zipfile.ZipFile(jar) as z:
            for name in ['assets/mmorpg/lang/en_us.json','assets/mmorpg/lang/ko_kr.json']:
                if name in z.namelist(): self.lang.update(json.loads(z.read(name)))
            for kind, folder in FOLDERS.items():
                prefix = f'data/mmorpg/{folder}/'
                for name in z.namelist():
                    if name.startswith(prefix) and name.endswith('.json'):
                        self.db[kind][name[len(prefix):]] = json.loads(z.read(name), strict=False)
        self.sources.append({'file':jar.name,'sha256':hashlib.sha256(jar.read_bytes()).hexdigest()})
        for base in sorted((ROOT/'config/openloader/data').iterdir()):
            for kind, folder in FOLDERS.items():
                path=base/'data/mmorpg'/folder
                if path.exists():
                    for f in sorted(path.rglob('*.json')):
                        try:self.db[kind][f.relative_to(path).as_posix()]=json.loads(f.read_text(encoding='utf-8-sig'),strict=False)
                        except (ValueError,UnicodeError):continue
        for pack in sorted((ROOT/'resourcepacks').glob('*.zip')):
            if '한글' in pack.name or 'korean' in pack.name.lower():
                with zipfile.ZipFile(pack) as z:
                    for name in ['assets/mmorpg/lang/ko_kr.json']:
                        if name in z.namelist():self.lang.update(json.loads(z.read(name)))
        local_lang=ROOT/'output/CTE2_Multiplayer/src/main/resources/assets/cte2_multiplayer/shop_ko.json'
        if local_lang.exists():self.lang.update(json.loads(local_lang.read_text(encoding='utf-8')))
        for kind, files in self.db.items():
            resolved={}
            for path,d in sorted(files.items(),key=lambda kv:('/' in kv[0],kv[0])):
                if not isinstance(d,dict):continue
                key=d.get('id') or d.get('guid') or d.get('identifier') or d.get('data',{}).get('id')
                if key:
                    d['_path']=path
                    if key not in resolved or d.get('weight',1000)>0:resolved[key]=d
            self.db[kind]=resolved
        self.meta={k:d.get('data',d) for k,d in self.db['stats'].items()}
        for sid in ['health','mana','energy','armor','magic_shield','dodge','weapon_damage','health_regen',
                    'mana_regen','energy_regen','magic_shield_regen','gear_weapon_damage','armor_penetration','flat_physical_added_damage',
                    'flat_fire_added_damage','flat_water_added_damage','flat_lightning_added_damage','flat_chaos_added_damage']:
            self.meta.setdefault(sid,{'id':sid,'scaling':'NORMAL','min':0})
        for ele in ['physical','fire','water','lightning','chaos']:
            self.meta.setdefault('flat_'+ele+'_added_attack_damage',{'scaling':'NORMAL','min':0})
        for sid in ['strength','dexterity','intelligence','all_attributes']:
            self.meta.setdefault(sid,{'id':sid,'scaling':'CORE','min':0})
        self.grid={}
        for key,d in self.db['trees'].items():
            self.grid[key]={(x,y):token.strip() for y,row in enumerate(csv.reader(d.get('perks','').splitlines())) for x,token in enumerate(row) if token.strip() in self.db['perks']}
        self.balance=self.db['balance'].get('original_balance',{})
        self.public=self.make_public()

    def name(self,kind,key):
        if key in NAMES:return NAMES[key]
        groups={'skills':['spell'],'supports':['support','support_gem'],'auras':['aura','aura_gem'],
                'perks':['talent','perk'],'uniques':['unique_gear'],'stats':['stat'],'gear':['gear_type'],'gems':['gem']}.get(kind,[kind])
        for g in groups:
            for s in [f'mmorpg.{g}.{key}',f'mmorpg.{g}.{key}.name',f'mmorpg.{g}.{key}.name.name']:
                if s in self.lang:return clean(self.lang[s])
        d=self.db.get(kind,{}).get(key,{})
        if kind=='perks':
            if key in self.db['skills']:return self.name('skills',key)
            if d.get('stats'):return ' / '.join(dict.fromkeys(self.name('stats',s['stat']).replace('[VAL1]',str(s.get('v1',s.get('max','')))) for s in d['stats']))
        return clean(d.get('loc_name') or d.get('name') or key)

    def scale(self,sid,level):
        scaling=self.meta.get(sid,{}).get('scaling',self.meta.get(sid,{}).get('scale','NONE'))
        key={'NORMAL':'NORMAL_STAT_SCALING','CORE':'CORE_STAT_SCALING','SLOW':'SLOW_STAT_SCALING'}.get(scaling)
        if not key:return 1
        conf=self.balance.get(key,{})
        if conf.get('cap_to_max_lvl'):level=min(level,self.balance.get('MAX_LEVEL',100))
        return conf.get('base_scaling',1)+max(0,level-1)*conf.get('per_level_scaling',0)

    def exact(self,stat,roll,level):
        sid=stat.get('stat','');typ=stat.get('type','FLAT').upper()
        if 'v1' in stat:
            value=stat['v1'];scaled=stat.get('scale_to_lvl',False)
        else:
            value=stat.get('min',0)+(stat.get('max',0)-stat.get('min',0))*roll/100;scaled=True
        if typ=='FLAT' and scaled:value*=self.scale(sid,level)
        return {'stat':sid,'type':typ,'value':value}

    def make_public(self):
        output={}
        for kind in ['skills','supports','auras','perks','affixes','uniques','gear','gems']:
            rows=[]
            for key,d in self.db[kind].items():
                if kind=='skills' and (d.get('weight',1000)==0 or 'mercenary' in d['_path']):continue
                rows.append({'id':key,'name':self.name(kind,key),'kind':kind,
                             'stats':d.get('stats',d.get('unique_stats',d.get('base_stats',[]))),
                             'slot':d.get('base_gear',d.get('gear_slot','')),'type':d.get('type',''),
                             'max_rank':d.get('max_lvl',d.get('max_lvls',1)),
                             'tags':d.get('config',{}).get('tags',d.get('tags',{})).get('tags',[]),
                             'config':d.get('config',{}),'min_level':d.get('min_lvl',1),
                             'requirements':d.get('requirements',{}),'icon':d.get('icon',''),
                             'style':d.get('style',''),'is_entry':d.get('is_entry',False)})
            output[kind]=sorted(rows,key=lambda r:r['name'])
        translated={k.removeprefix('mmorpg.stat.') for k in self.lang if k.startswith('mmorpg.stat.') and '.' not in k.removeprefix('mmorpg.stat.')}
        output['stat_names']={k:self.name('stats',k) for k in set(self.meta)|set(NAMES)|translated}
        output['sources']=self.sources
        output['version']='0.2.1'
        return output

def get_catalog():
    global _catalog
    if '_catalog' not in globals():_catalog=Catalog()
    return _catalog
