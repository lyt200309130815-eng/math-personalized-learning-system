"""Real KaTeX DOM audit of every trainable question field on a disposable DB."""
from contextlib import closing
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.smoke_multitype_browser import Browser


def smoke(database_path):
    def port():
        with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
    folder=ROOT/'tmp'/('v1_0d_4_bank_browser_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'));folder.mkdir(parents=True)
    entry=folder/'render_bank.py'
    entry.write_text('''import sys
from pathlib import Path
sys.path.insert(0,''' + repr(str(ROOT)) + ''')
import streamlit as st
from database.database import get_approved_questions
from services.math_normalizer import FIELDS
from services.math_text import render_math_text
st.title('公式渲染验收')
def show(value):
    if isinstance(value,str): render_math_text(value)
    elif isinstance(value,list):
        for v in value: show(v)
    elif isinstance(value,dict):
        for v in value.values(): show(v)
for q in get_approved_questions(taxonomy_version='function_v2'):
    st.subheader(q['id'])
    for field in FIELDS:
        if field in q: show(q[field])
st.write('FORMULA_AUDIT_COMPLETE')
''',encoding='utf-8')
    web,debug=port(),port();env=dict(os.environ);env.update(MATH_AI_DATABASE_PATH=str(Path(database_path).resolve()),ACTIVE_TAXONOMY_VERSION='function_v2')
    log=(folder/'server.log').open('w',encoding='utf-8');edge_log=(folder/'edge.log').open('w',encoding='utf-8')
    server=subprocess.Popen([sys.executable,'-m','streamlit','run',str(entry),'--server.headless=true',f'--server.port={web}','--browser.gatherUsageStats=false'],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    process=None;b=None
    try:
        for _ in range(80):
            try:urllib.request.urlopen(f'http://127.0.0.1:{web}/_stcore/health',timeout=1);break
            except OSError:time.sleep(.25)
        process=subprocess.Popen(['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','--headless=new','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update','--disable-sync',f'--remote-debugging-port={debug}','--remote-allow-origins=*','--user-data-dir='+str(folder/'edge_profile'),'about:blank'],stdout=edge_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(80):
            try:tab=next(t for t in json.load(urllib.request.urlopen(f'http://127.0.0.1:{debug}/json',timeout=1)) if t.get('type')=='page');break
            except (OSError,StopIteration):time.sleep(.25)
        b=Browser(tab['webSocketDebuggerUrl']);b.call('Page.enable');b.call('Page.navigate',{'url':f'http://127.0.0.1:{web}/'})
        b.wait('document.body.innerText.includes("FORMULA_AUDIT_COMPLETE")',timeout=60)
        errors=b.evaluate('Array.from(document.querySelectorAll(".katex-error")).map(e=>({text:e.innerText,title:e.title}))')
        result={'result':'passed' if not errors else 'failed','rendered_math_count':b.evaluate('document.querySelectorAll(".katex").length'),'katex_errors':errors,'folder':str(folder)}
        (ROOT/'reports/v1_0d_4_katex_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True),flush=True)
        if errors:raise AssertionError('KaTeX errors detected')
        return result
    finally:
        if b:b.ws.close()
        if process:process.terminate();process.wait(timeout=15)
        server.terminate();server.wait(timeout=15);log.close();edge_log.close()


if __name__=='__main__':smoke(sys.argv[1] if len(sys.argv)>1 else ROOT/'tmp/v1_0d_4/test.sqlite3')
