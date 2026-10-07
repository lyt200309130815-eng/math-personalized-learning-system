"""Real headless Edge/Streamlit UI acceptance on an isolated production backup."""
from contextlib import closing
from datetime import datetime,timezone
from io import BytesIO
import base64
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import time
import urllib.request

import websocket
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from database.database import get_connection,get_approved_questions,record_attempt
from database.training_sessions import save_session
from services.adaptive_training import start_training_session,end_training_session
from services.answer_evaluator import parse_math
from services.mastery import calculate_knowledge_mastery
from scripts.integrate_multitype_production import integrate,snapshot


class Browser:
    def __init__(self,url):
        self.ws=websocket.create_connection(url.replace('localhost','127.0.0.1'),timeout=15,
                                            http_no_proxy=['localhost','127.0.0.1']);self.sequence=0
    def call(self,method,params=None):
        self.sequence+=1;identity=self.sequence
        self.ws.send(json.dumps({'id':identity,'method':method,'params':params or {}}))
        while True:
            message=json.loads(self.ws.recv())
            if message.get('id')==identity:
                if 'error' in message:raise RuntimeError(message['error'])
                return message.get('result',{})
    def evaluate(self,expression):
        r=self.call('Runtime.evaluate',{'expression':expression,'returnByValue':True})
        if r.get('exceptionDetails'):raise RuntimeError(r['exceptionDetails'])
        return r.get('result',{}).get('value')
    def wait(self,expression,timeout=30):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if self.evaluate(expression):return
            time.sleep(.25)
        raise TimeoutError(expression+'\n'+str(self.evaluate('document.body.innerText'))[-2500:])
    def click_text(self,text):
        self.wait('Array.from(document.querySelectorAll("button")).some(b=>b.innerText.trim()==='+json.dumps(text)+')')
        self.evaluate('Array.from(document.querySelectorAll("button")).find(b=>b.innerText.trim()==='+json.dumps(text)+').click()')
    def input(self,selector,value):
        self.wait('!!document.querySelector('+json.dumps(selector)+')')
        root=self.call('DOM.getDocument')['root']['nodeId']
        node=self.call('DOM.querySelector',{'nodeId':root,'selector':selector})['nodeId']
        self.call('DOM.focus',{'nodeId':node})
        self.evaluate('document.querySelector('+json.dumps(selector)+').select()')
        self.call('Input.insertText',{'text':value})
        print('answer widget after typing: '+str(self.evaluate('document.querySelector('+json.dumps(selector)+').value')),flush=True)
        self.evaluate('document.querySelector('+json.dumps(selector)+').blur()')
        time.sleep(.7)


def smoke():
    def free_port():
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));return s.getsockname()[1]
    web_port=free_port();debug_port=free_port()
    folder=ROOT/'tmp'/('v1_0d_2_browser_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    folder.mkdir(parents=True,exist_ok=False);path=folder/'browser.sqlite3'
    with closing(get_connection(ROOT/'math_ai.db',read_only=True)) as original,closing(get_connection(path)) as target:
        original_before=snapshot(original);original.backup(target)
    integrate(path)
    questions=get_approved_questions(database_path=path,taxonomy_version='function_v2')
    selected={kind:next(q for q in questions if q['question_type']==kind and
                       (kind!='subjective' or len(q.get('sub_questions',[]))>=2) and
                       (kind!='fill_blank' or q['answer_type']=='numeric' and '/' in q['canonical_answer']
                        and parse_math(q['canonical_answer']).is_Rational is True))
              for kind in ('single_choice','multiple_choice','fill_blank','subjective')}
    env=dict(os.environ);env.update(MATH_AI_DATABASE_PATH=str(path),ACTIVE_TAXONOMY_VERSION='function_v2',STREAMLIT_BROWSER_GATHER_USAGE_STATS='false')
    env.pop('OPENAI_API_KEY',None);env.pop('DEEPSEEK_API_KEY',None)
    streamlit_log=(folder/'streamlit.log').open('w',encoding='utf-8')
    edge_log=(folder/'edge.log').open('w',encoding='utf-8')
    server=subprocess.Popen([sys.executable,'-m','streamlit','run',str(ROOT/'app.py'),'--server.headless=true',f'--server.port={web_port}','--browser.gatherUsageStats=false'],cwd=ROOT,env=env,stdout=streamlit_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    browser_process=None;browser=None;results=[]
    try:
        for _ in range(80):
            try:
                if server.poll() is not None:raise RuntimeError('验收 Streamlit 服务启动失败。')
                urllib.request.urlopen(f'http://127.0.0.1:{web_port}/_stcore/health',timeout=1);break
            except OSError:time.sleep(.25)
        edge=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
        browser_process=subprocess.Popen([str(edge),'--headless=new','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update','--disable-sync',f'--remote-debugging-port={debug_port}','--remote-allow-origins=*','--user-data-dir='+str(folder/'edge_profile'),'about:blank'],stdout=edge_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        tab=None
        for _ in range(80):
            try:
                if browser_process.poll() is not None:raise RuntimeError('验收 Edge 启动失败。')
                tabs=json.load(urllib.request.urlopen(f'http://127.0.0.1:{debug_port}/json',timeout=1))
                tab=next(t for t in tabs if t.get('type')=='page');break
            except (OSError,StopIteration):time.sleep(.25)
        if tab is None:raise RuntimeError('浏览器调试连接未就绪。')
        browser=Browser(tab['webSocketDebuggerUrl']);browser.call('Page.enable')
        browser.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
        for kind,q in selected.items():
            student='S001'
            # All scenario evidence is synthetic and confined to the copied DB.
            from database.training_sessions import get_latest_session
            previous=get_latest_session(student,database_path=path)
            if previous and previous['status']=='active':end_training_session(student,previous['id'],database_path=path)
            for key in sorted({r['knowledge_point_id'] for r in questions}):
                seed=next(r for r in questions if r['knowledge_point_id']==key and r['question_type']=='single_choice')
                for _ in range(8):record_attempt(student,seed['id'],seed['answer'],1,3.,database_path=path)
            state=start_training_session(student,target_knowledge_point_id=q['knowledge_point_id'],database_path=path,lock_target=True)
            state.update(current_question=q,submitted=False,question_started_at=time.time(),selection_note='隔离网页验收',question_hint_count=0,question_retry_count=0)
            with closing(get_connection(path)) as c,c:
                c.execute('INSERT INTO training_session_questions(session_id,question_id,sequence_no,difficulty) VALUES (?,?,1,?)',(state['id'],q['id'],q['difficulty']))
                save_session(c,state)
            before_mastery=calculate_knowledge_mastery(student,q['knowledge_point_id'],database_path=path,taxonomy_version='function_v2')
            # Initialize st.navigation through the entry point before a page URL.
            browser.call('Page.navigate',{'url':f'http://127.0.0.1:{web_port}/'})
            browser.wait('!!document.querySelector("[data-testid=stSidebar] [data-testid=stTextInput] input")')
            browser.wait('Array.from(document.querySelectorAll("a")).some(a=>a.innerText.trim()==="开始训练")')
            browser.evaluate('Array.from(document.querySelectorAll("a")).find(a=>a.innerText.trim()==="开始训练").click()')
            browser.wait('document.body.innerText.includes("隔离网页验收")')
            if kind=='single_choice':
                browser.wait('document.querySelectorAll("[data-testid=stRadio] input[type=radio]").length===4')
                browser.evaluate(f'document.querySelectorAll("[data-testid=stRadio] input[type=radio]")[{"ABCD".index(q["answer"])}].click()')
            elif kind=='multiple_choice':
                browser.wait('!!document.querySelector("[data-testid=stMultiSelect] input")')
                for letter in reversed(q['correct_answers']):
                    browser.evaluate('document.querySelector("[data-testid=stMultiSelect] input").focus();document.querySelector("[data-testid=stMultiSelect] input").click()')
                    browser.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'ArrowDown','code':'ArrowDown','windowsVirtualKeyCode':40})
                    browser.wait('document.querySelectorAll("[role=option]").length>0')
                    # Options display the submitted letters with their original math text.
                    expression='Array.from(document.querySelectorAll("[role=option]")).find(o=>o.innerText.trim().startsWith('+json.dumps(letter+'.')+')).click()'
                    browser.evaluate(expression);time.sleep(.3)
            elif kind=='fill_blank':
                value=str(parse_math(q['canonical_answer']).evalf(15))
                # Use an exact terminating decimal when available, otherwise equivalent fraction.
                expected=parse_math(q['canonical_answer']);denominator=int(expected.q) if hasattr(expected,'q') else 1
                rest=denominator
                for divisor in (2,5):
                    while rest%divisor==0 and rest>1:rest//=divisor
                if rest!=1:value=str(expected)
                browser.input('[data-testid=stMain] [data-testid=stTextInput] input',value)
                if browser.evaluate('document.querySelectorAll("[data-testid=stRadio]").length'):raise AssertionError('填空出现选项')
            else:
                browser.wait('document.body.innerText.includes("总分")')
                browser.input('textarea','从函数定义出发，列出条件并逐步求解。（隔离验收文本）')
                image=folder/'synthetic_handwriting.png';Image.new('RGB',(100,50),'white').save(image)
                root=browser.call('DOM.getDocument')['root']['nodeId']
                node=browser.call('DOM.querySelector',{'nodeId':root,'selector':'input[type=file]'})['nodeId']
                browser.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(image)]})
                browser.wait('document.body.innerText.includes("解题图片预览")')
            browser.click_text('提交答案')
            browser.wait('document.body.innerText.includes('+json.dumps('待评阅' if kind=='subjective' else '回答正确')+')')
            with closing(get_connection(path,read_only=True)) as c:
                record=dict(c.execute('SELECT * FROM attempts WHERE student_id=? ORDER BY id DESC LIMIT 1',(student,)).fetchone())
                if kind=='subjective':
                    submission=dict(c.execute('SELECT * FROM subjective_submissions WHERE attempt_id=?',(record['id'],)).fetchone())
                    if not Path(submission['attachment_path']).is_file() or submission['status']!='submitted_pending_review':raise AssertionError('图片或待评阅未保存')
            after_mastery=calculate_knowledge_mastery(student,q['knowledge_point_id'],database_path=path,taxonomy_version='function_v2')
            if kind=='subjective' and before_mastery!=after_mastery:raise AssertionError('大题污染 mastery')
            png=browser.call('Page.captureScreenshot',{'format':'png'})['data']
            screenshot=folder/(kind+'.png');screenshot.write_bytes(base64.b64decode(png))
            results.append({'question_type':kind,'question_id':q['id'],'result':'passed','correctness':record['is_correct'],
                            'screenshot':str(screenshot),'image_upload_verified':kind=='subjective',
                            'pending_mastery_unchanged':before_mastery==after_mastery if kind=='subjective' else None})
            print(kind+' browser passed',flush=True)
            end_training_session(student,state['id'],database_path=path)
        with closing(get_connection(ROOT/'math_ai.db',read_only=True)) as original:
            if snapshot(original)!=original_before:raise AssertionError('网页验收期间生产作答变化')
        report={'stage':'V1.0D.2','browser':'Microsoft Edge headless via CDP','streamlit_real_http':True,
                'database_isolated_copy':True,'production_attempts_written':0,'ocr_called':False,'cases':results}
        (ROOT/'reports/v1_0d_2_browser_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return report
    finally:
        if browser:browser.ws.close()
        if browser_process:browser_process.terminate();browser_process.wait(timeout=15)
        server.terminate();server.wait(timeout=15);streamlit_log.close();edge_log.close()


if __name__=='__main__':print(json.dumps(smoke(),ensure_ascii=True,indent=2))
