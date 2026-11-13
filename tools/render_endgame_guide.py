"""Render the maintained Korean endgame Markdown without network dependencies."""
from pathlib import Path
import html,re

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'docs/endgame/guide.md'
def inline(value):
    value=html.escape(value)
    value=re.sub(r'`([^`]+)`',r'<code>\1</code>',value)
    return re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',value)
def render():
    chunks=[]; lines=SOURCE.read_text('utf-8').splitlines(); i=0;toc=[]
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith('# '):chunks.append('<h1>'+inline(line[2:])+'</h1>');i+=1;continue
        if line.startswith('## '):
            anchor='section-'+str(len(toc)+1);label=line[3:];toc.append((anchor,label));chunks.append(f'<h2 id="{anchor}">'+inline(label)+'</h2>');i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=[x.strip() for x in lines[i].strip().strip('|').split('|')];i+=1
                if all(re.fullmatch(r':?-+:?',c) for c in row):continue
                rows.append(row)
            chunks.append('<div class="table"><table><thead><tr>'+''.join('<th>'+inline(c)+'</th>' for c in rows[0])+'</tr></thead><tbody>')
            for row in rows[1:]:chunks.append('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>')
            chunks.append('</tbody></table></div>');continue
        if line.startswith('- ') or re.match(r'^\d+\. ',line):
            ordered=not line.startswith('- ');tag='ol' if ordered else 'ul';chunks.append('<'+tag+'>')
            while i<len(lines) and (bool(re.match(r'^\d+\. ',lines[i])) if ordered else lines[i].startswith('- ')):
                text=re.sub(r'^(?:- |\d+\. )','',lines[i]);chunks.append('<li>'+inline(text)+'</li>');i+=1
            chunks.append('</'+tag+'>');continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','- ')) and not re.match(r'^\d+\. ',lines[i]):paragraph.append(lines[i].strip());i+=1
        chunks.append('<p>'+inline(' '.join(paragraph))+'</p>')
    nav='<nav aria-label="목차">'+''.join('<a href="#'+a+'">'+inline(label)+'</a>' for a,label in toc)+'</nav>'
    shell='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CTE2 최종 도전 공략</title><meta name="description" content="초월정점, 4인 공략 보스, 개인시련 10단계, 지도 시련 스피드런의 한국어 공략과 운영 안내"><style>
    :root{color-scheme:dark}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#101820;color:#e4ece8;font:16px/1.85 system-ui,-apple-system,'Malgun Gothic',sans-serif}header,main,footer{max-width:1100px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;border-bottom:1px solid #40544b}a{color:#f0dca2;text-underline-offset:4px}h1{color:#f0dca2;font-size:clamp(28px,4vw,44px);line-height:1.35;margin:35px 0 20px}h2{color:#d7e9db;border-top:1px solid #40544b;padding-top:30px;margin-top:45px;scroll-margin-top:20px}p,li{max-width:88ch}li{margin:10px 0}nav{display:flex;flex-wrap:wrap;gap:10px;margin:24px 0}nav a{padding:6px 12px;border:1px solid #506650;border-radius:4px}code{font-size:.91em;background:#233039;color:#f3dfad;padding:2px 5px;border-radius:3px;overflow-wrap:anywhere}.table{overflow-x:auto;margin:24px 0}table{border-collapse:collapse;width:100%;min-width:620px;background:#18252c}th,td{text-align:left;border:1px solid #465b56;padding:12px 14px;vertical-align:top}th{color:#f0dca2;background:#21352f}footer{border-top:1px solid #40544b;color:#a5b9ad;font-size:14px}.badge{display:inline-block;border:1px solid #b79a5b;color:#f0dca2;padding:3px 10px;border-radius:3px}@media(max-width:640px){header,main,footer{padding:18px}header{font-size:14px;gap:18px}h2{font-size:22px}}
    </style></head><body><header><a href="../">CTE2 자료실</a><a href="https://github.com/piro0101/CTE2-Multi#readme">설치 · 업데이트</a></header><main><span class="badge">게임 수정본 0.4.1 · 플레이테스트</span>'''
    # Keep the heading before its table of contents.
    (ROOT/'docs/endgame/index.html').write_text(shell+chunks[0]+'<img src="./ascended-map-upgrade.png" width="80" height="80" alt="초월정점 지도 강화 오브" style="image-rendering:pixelated"><p>검은 강화 오브 + 미사용 정점 지도 → 초월정점 지도 → 원래 지도 장치 입장</p>'+nav+'\n'.join(chunks[1:])+'''<p><a href="./guide.md">설명서 원문 내려받기</a></p></main><footer>기준: CTE2 2.1.4 · Minecraft 1.20.1 · Forge 47.4.23. 실제 4인 전투·30명 동시 부하 검증은 별도로 필요합니다.</footer></body></html>''','utf-8')
if __name__=='__main__':render();print('Rendered Korean endgame guide')
