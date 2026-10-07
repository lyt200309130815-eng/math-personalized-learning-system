"""Complete the real mixed diagnostic and eight practice questions on a DB copy."""
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from PIL import Image
from scripts.smoke_multitype_browser import Browser
from scripts.integrate_multitype_production import snapshot
from database.database import get_connection
from database.diagnostic import load_latest
from database.training_sessions import get_latest_session
from services.adaptive_training import end_training_session
from services.mastery import calculate_student_mastery


def smoke(*, stage='V1.0D.3', practice_count=8):
    def port():
        with socket.socket() as s: s.bind(('127.0.0.1',0)); return s.getsockname()[1]
    web,debug=port(),port()
    stage_key=stage.lower().replace('.','_')
    student=stage_key.upper()+'_BROWSER_FRESH'
    folder=ROOT/'tmp'/(stage_key+'_browser_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    folder.mkdir(parents=True); path=folder/'browser.db'
    with closing(get_connection(ROOT/'math_ai.db',read_only=True)) as src, closing(get_connection(path)) as dst:
        before=snapshot(src); src.backup(dst)
    previous=get_latest_session(student,database_path=path)
    if previous and previous['status']=='active': end_training_session(student,previous['id'],database_path=path)
    env=dict(os.environ);env.update(MATH_AI_DATABASE_PATH=str(path),ACTIVE_TAXONOMY_VERSION='function_v2')
    for key in ('OPENAI_API_KEY','DEEPSEEK_API_KEY','GEMINI_API_KEY'): env.pop(key,None)
    stream_log=(folder/'streamlit.log').open('w',encoding='utf-8');edge_log=(folder/'edge.log').open('w',encoding='utf-8')
    # Same application and pages, with a fresh fixture student as the default.
    # Keep the entry point beside app.py so Streamlit relative navigation works.
    entry=ROOT/('_browser_fixture_'+folder.name+'.py')
    entry.write_text((ROOT/'app.py').read_text(encoding='utf-8').replace("value='S001'",f"value='{student}'"),encoding='utf-8')
    server=subprocess.Popen([sys.executable,'-m','streamlit','run',str(entry),'--server.headless=true',f'--server.port={web}','--browser.gatherUsageStats=false'],cwd=ROOT,env=env,stdout=stream_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    process=None;browser=None
    try:
        for _ in range(80):
            try: urllib.request.urlopen(f'http://127.0.0.1:{web}/_stcore/health',timeout=1);break
            except OSError: time.sleep(.25)
        process=subprocess.Popen(['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','--headless=new','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update','--disable-sync',f'--remote-debugging-port={debug}','--remote-allow-origins=*','--user-data-dir='+str(folder/'edge_profile'),'about:blank'],stdout=edge_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        tab=None
        for _ in range(80):
            try: tab=next(t for t in json.load(urllib.request.urlopen(f'http://127.0.0.1:{debug}/json',timeout=1)) if t.get('type')=='page');break
            except (OSError,StopIteration): time.sleep(.25)
        if not tab: raise RuntimeError('Edge未启动')
        browser=Browser(tab['webSocketDebuggerUrl']);browser.call('Page.enable')
        browser.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
        browser.call('Page.navigate',{'url':f'http://127.0.0.1:{web}/'})
        browser.wait('!!document.querySelector("[data-testid=stSidebar] [data-testid=stTextInput] input")')
        browser.wait('document.querySelector("[data-testid=stSidebar] [data-testid=stTextInput] input").value==='+json.dumps(student))
        browser.wait('Array.from(document.querySelectorAll("a")).some(a=>a.innerText.trim()==="首次诊断")')
        browser.evaluate('Array.from(document.querySelectorAll("a")).find(a=>a.innerText.trim()==="首次诊断").click()')
        browser.wait('document.body.innerText.includes("函数知识诊断测评")')
        state=load_latest(student,path)
        if state is None: browser.click_text('开始诊断')
        elif state['diagnostic_completed']: browser.click_text('重新诊断')
        browser.wait('document.body.innerText.includes("第 1 / 18 题")')
        diagnostic=[];practice=[];uploaded=False
        image=folder/'synthetic_handwriting.png';Image.new('RGB',(100,50),'white').save(image)

        def check_math():
            if stage!='V1.0D.4':return
            time.sleep(.2)
            errors=browser.evaluate('Array.from(document.querySelectorAll(".katex-error")).map(e=>e.title)')
            leftovers=browser.evaluate(r'''(()=>{let main=document.querySelector('[data-testid=stMain]');let walker=document.createTreeWalker(main,NodeFilter.SHOW_TEXT);let bad=[];let n;while(n=walker.nextNode()){if(n.parentElement.closest('.katex,textarea,input,script,style,svg'))continue; if(/\$|\^\(|\)\s*\/\s*\(|(?:a?root|sqrt)\(/.test(n.textContent))bad.push(n.textContent);}return bad;})()''')
            if errors or leftovers:raise AssertionError('数学显示异常：'+json.dumps({'errors':errors,'raw':leftovers},ensure_ascii=False))

        def answer(q,correct=True):
            nonlocal uploaded
            kind=q['question_type']
            browser.wait('Array.from(document.querySelectorAll("button")).some(b=>b.innerText.trim()==="提交答案"&&!b.disabled)')
            check_math()
            if kind=='single_choice':
                browser.wait('document.querySelectorAll("[data-testid=stRadio] input[type=radio]").length===4')
                value=q['answer'] if correct else next(c for c in 'ABCD' if c!=q['answer'])
                browser.evaluate(f'document.querySelectorAll("[data-testid=stRadio] input[type=radio]")[{"ABCD".index(value)}].click()')
            elif kind=='multiple_choice':
                browser.wait('document.querySelectorAll("[data-testid=stCheckbox] input").length===4')
                values=q['correct_answers'] if correct else ['A'] if set(q['correct_answers'])!={'A'} else ['B']
                for value in reversed(values):
                    browser.evaluate(f'document.querySelectorAll("[data-testid=stCheckbox] input")[{"ABCD".index(value)}].click()');time.sleep(.2)
            elif kind=='fill_blank':
                browser.wait('!!document.querySelector("[data-testid=stMain] [data-testid=stTextInput] input")')
                if browser.evaluate('document.querySelectorAll("[data-testid=stRadio], [data-testid=stCheckbox]").length'): raise AssertionError('填空题显示选项')
                from services.math_normalizer import evaluator_math_text
                browser.input('[data-testid=stMain] [data-testid=stTextInput] input',evaluator_math_text(q['canonical_answer']) if correct else '999999')
            else:
                browser.wait('!!document.querySelector("textarea")')
                if browser.evaluate('document.querySelectorAll("[data-testid=stRadio], [data-testid=stCheckbox]").length'): raise AssertionError('大题显示选项')
                browser.input('textarea','先由题设列出函数条件，再分小问求解。')
                if not uploaded:
                    root=browser.call('DOM.getDocument')['root']['nodeId'];node=browser.call('DOM.querySelector',{'nodeId':root,'selector':'input[type=file]'})['nodeId']
                    browser.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(image)]})
                    browser.wait('document.body.innerText.includes("解题图片预览")');uploaded=True
            time.sleep(.4);browser.click_text('提交答案')

        for index in range(18):
            state=load_latest(student,path);q=state['current_question'];qid=q['id']
            browser.wait(f'document.body.innerText.includes("第 {index+1} / 18 题")')
            mastery=calculate_student_mastery(student,database_path=path,taxonomy_version='function_v2')
            answer(q)
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                saved=load_latest(student,path)
                if any(a['question_id']==qid for a in saved['answers']):break
                time.sleep(.2)
            else:raise AssertionError('诊断提交未保存')
            record=next(a for a in saved['answers'] if a['question_id']==qid)
            if q['question_type']=='subjective' and mastery!=calculate_student_mastery(student,database_path=path,taxonomy_version='function_v2'):raise AssertionError('主观题污染诊断掌握度')
            diagnostic.append({'question_id':qid,'question_type':q['question_type'],'is_correct':record['is_correct']})
            print(f'diagnostic {index+1}/18 {q["question_type"]} passed',flush=True)
        browser.wait('document.body.innerText.includes("诊断完成")')
        (folder/'diagnostic_result.png').write_bytes(base64.b64decode(browser.call('Page.captureScreenshot',{'format':'png'})['data']))
        browser.click_text('开始针对性训练')
        auto_index=0
        for index in range(practice_count):
            browser.wait('document.body.innerText.includes("自适应函数训练")')
            state=get_latest_session(student,database_path=path)
            if state['status']!='active':
                previous_id=state['id']
                browser.click_text('开始个性化训练')
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    state=get_latest_session(student,database_path=path)
                    if state['id']!=previous_id and state['current_question']:break
                    time.sleep(.2)
                else:raise AssertionError('后续训练未开始')
            q=state['current_question']
            if not q:
                time.sleep(.5);state=get_latest_session(student,database_path=path);q=state['current_question']
            if not q:raise AssertionError('训练未选择下一题')
            qid=q['id']; correct=auto_index%2==0
            if q['question_type']!='subjective': auto_index+=1
            streaks=(state['correct_streak'],state['wrong_streak'],state['difficulty'])
            answer(q,correct)
            browser.wait('document.body.innerText.includes('+json.dumps('当前等待评阅' if q['question_type']=='subjective' else '回答正确' if correct else '回答错误')+')')
            saved=get_latest_session(student,database_path=path);record=saved['answers'][-1]
            if record['question_id']!=qid:raise AssertionError('作答题目错误')
            if record['is_correct'] is None and streaks!=(saved['correct_streak'],saved['wrong_streak'],saved['difficulty']):raise AssertionError('待评阅影响即时难度')
            practice.append({'question_id':qid,'question_type':q['question_type'],'is_correct':record['is_correct']})
            print(f'adaptive {index+1}/{practice_count} {q["question_type"]} passed',flush=True)
            if index+1>=practice_count:break
            if saved['status']!='active':continue
            browser.click_text('下一题')
            browser.wait(f'document.body.innerText.includes("第 {len(saved["answers"])+1} / 8 题")')
        if len(practice)<practice_count:raise AssertionError(f'实际训练题数不足：{len(practice)}')
        dm=Counter(q['question_type'] for q in diagnostic);am=Counter(q['question_type'] for q in practice)
        if len({q['question_type'] for q in diagnostic[:8]})<2 or not am['fill_blank'] or not(am['single_choice']+am['multiple_choice']):raise AssertionError('实际题型不足')
        diagnosed={q['question_id'] for q in diagnostic};repeated=[q['question_id'] for q in practice if q['question_id'] in diagnosed]
        if repeated:raise AssertionError('诊断题马上重复：'+str(repeated))
        with closing(get_connection(path,read_only=True)) as c:
            attachments=[dict(r) for r in c.execute("SELECT attachment_path,status FROM subjective_submissions WHERE student_id=? AND attachment_path IS NOT NULL",(student,))]
            if not any(Path(r['attachment_path']).is_file() for r in attachments):raise AssertionError('上传图片引用未保存')
        with closing(get_connection(ROOT/'math_ai.db',read_only=True)) as c:
            if snapshot(c)!=before:raise AssertionError('真实数据库发生变化')
        (folder/'adaptive_result.png').write_bytes(base64.b64decode(browser.call('Page.captureScreenshot',{'format':'png'})['data']))
        report={'stage':stage,'result':'passed','browser':'Microsoft Edge headless / real Streamlit HTTP','isolated_database':str(path),'diagnostic_mix':dict(dm),'adaptive_mix':dict(am),'diagnostic':diagnostic,'adaptive':practice,'first_8_multiple_types':True,'uploaded_image_saved':uploaded,'immediate_repeats':repeated,'production_snapshot_unchanged':True,'production_snapshot':before,'screenshots_directory':str(folder),'formula_dom_checked':stage=='V1.0D.4'}
        (ROOT/f'reports/{stage_key}_browser_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Diagnostic question mix:',dict(dm)); print('Adaptive session mix:',dict(am));return report
    finally:
        if browser:browser.ws.close()
        if process:process.terminate();process.wait(timeout=15)
        server.terminate();server.wait(timeout=15);stream_log.close();edge_log.close()
        if entry.resolve().parent==ROOT.resolve(): entry.unlink(missing_ok=True)


if __name__=='__main__':
    print(json.dumps(smoke(stage='V1.0D.4',practice_count=10) if '--formula-cleanup' in sys.argv else smoke(),ensure_ascii=True,indent=2))
