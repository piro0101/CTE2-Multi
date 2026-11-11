import {loadPyodide} from 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs';

const ready=(async()=>{
  const py=await loadPyodide({indexURL:'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/'});
  py.FS.mkdirTree('/app');
  const modules=['catalog','engine','game','inspector','importer','build_storage','browser_api'];
  await Promise.all(modules.map(async name=>{const r=await fetch(new URL(`python/${name}.py`,import.meta.url));if(!r.ok)throw Error('계산 모듈을 불러오지 못했습니다.');py.FS.writeFile(`/app/${name}.py`,await r.text());}));
  const snapshot=await fetch(new URL('catalog-snapshot.json',import.meta.url));if(!snapshot.ok)throw Error('게임 데이터를 불러오지 못했습니다.');
  py.FS.writeFile('/app/catalog-snapshot.json',await snapshot.text());
  await py.runPythonAsync(`
import sys, json, csv
sys.path.insert(0, '/app')
import catalog
c = catalog.Catalog.__new__(catalog.Catalog)
c.__dict__.update(json.loads(open('/app/catalog-snapshot.json', encoding='utf-8').read()))
c.grid = {key: {(x,y): token.strip() for y,row in enumerate(csv.reader(d.get('perks','').splitlines())) for x,token in enumerate(row) if token.strip() in c.db['perks']} for key,d in c.db['trees'].items()}
catalog._catalog = c
import browser_api
`);
  return py;
})();
let queue=Promise.resolve();
self.onmessage=event=>{
  const request=event.data;
  queue=queue.then(async()=>{
    try{
      const py=await ready;
      py.globals.set('request_json',JSON.stringify(request));
      const result=await py.runPythonAsync("json.dumps(browser_api.dispatch(json.loads(request_json)), ensure_ascii=False, allow_nan=False)");
      self.postMessage({id:request.id,result:JSON.parse(result)});
    }catch(error){self.postMessage({id:request.id,error:String(error.message||error)});}
  });
};
