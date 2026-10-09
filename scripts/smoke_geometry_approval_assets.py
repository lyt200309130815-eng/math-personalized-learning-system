"""Render reviewed recovery content in headless Edge; no DB writes/imports."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.smoke_multitype_browser import Browser
from services.geometry_review import read_rows
from services.question_assets import visible_assets


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def smoke():
    folder = ROOT / 'tmp' / ('geometry_v1_1e_assets_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    folder.mkdir(parents=True)
    rows = read_rows(ROOT / 'data/question_bank/geometry_v1_1e/approved_ready.jsonl')
    entry = folder / 'review_preview.py'
    entry.write_text('''import sys
from pathlib import Path
sys.path.insert(0, ''' + repr(str(ROOT)) + ''')
import streamlit as st
from services.geometry_review import read_rows, ROOT
from services.math_text import render_math_text
from services.question_assets import visible_assets
st.set_page_config(page_title='恢复题审核预览')
st.title('恢复题production回归预览')
st.caption('正式批准题全量渲染回归，不保存学生作答。')
solution = st.checkbox('显示答案与解析（审核）')
for q in read_rows(ROOT/'data/question_bank/geometry_v1_1e/approved_ready.jsonl'):
    st.subheader(q['id'])
    render_math_text(q['stem'])
    for sub in q.get('sub_questions', []): render_math_text(sub['stem'])
    for letter, value in (q.get('options') or {}).items(): render_math_text(letter+'. '+value)
    for a in visible_assets(q):
        st.image(str(ROOT/a['path']), caption='选项图' if a['role']=='option_image' else '题图')
    if solution:
        render_math_text('答案：'+str(q.get('answer') or q.get('correct_answers') or q.get('canonical_answer') or q.get('reference_answer')))
        render_math_text(q['explanation'])
        for a in visible_assets(q, solution=True):
            st.image(str(ROOT/a['path']), caption='解析图')
st.write('GEOMETRY_REVIEW_COMPLETE_'+str(solution))
''', encoding='utf-8')
    web, debug = free_port(), free_port()
    environment = dict(os.environ)
    for key in ('OPENAI_API_KEY', 'DEEPSEEK_API_KEY', 'GEMINI_API_KEY'):
        environment.pop(key, None)
    server_log = (folder / 'streamlit.log').open('w', encoding='utf-8')
    edge_log = (folder / 'edge.log').open('w', encoding='utf-8')
    server = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(entry), '--server.headless=true',
                               f'--server.port={web}', '--browser.gatherUsageStats=false'], cwd=ROOT, env=environment,
                              stdout=server_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    edge = browser = None
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{web}/_stcore/health', timeout=1)
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Preview Streamlit failed')
                time.sleep(.25)
        edge = subprocess.Popen(['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', '--headless=new',
                                 '--disable-gpu', '--no-first-run', '--disable-background-networking', '--disable-component-update',
                                 '--disable-sync', f'--remote-debugging-port={debug}', '--remote-allow-origins=*',
                                 '--user-data-dir=' + str(folder / 'edge_profile'), 'about:blank'],
                                stdout=edge_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        tab = None
        for _ in range(80):
            try:
                tab = next(t for t in json.load(urllib.request.urlopen(f'http://127.0.0.1:{debug}/json', timeout=1)) if t.get('type') == 'page')
                break
            except (OSError, StopIteration):
                if edge.poll() is not None:
                    raise RuntimeError('Headless Edge exited; see ' + str(folder / 'edge.log'))
                time.sleep(.25)
        if tab is None:
            raise RuntimeError('Headless Edge debugging port unavailable')
        browser = Browser(tab['webSocketDebuggerUrl'])
        browser.call('Page.enable')
        browser.call('Page.navigate', {'url': f'http://127.0.0.1:{web}/'})
        browser.wait('document.body.innerText.includes("GEOMETRY_REVIEW_COMPLETE_False")', timeout=60)
        before = sum(len(visible_assets(q)) for q in rows)
        browser.wait('document.querySelectorAll("[data-testid=stImage] img").length===' + str(before))
        assert browser.evaluate('!document.body.innerText.includes("解析图")')
        assert browser.evaluate('Array.from(document.querySelectorAll("[data-testid=stImage] img")).every(i=>i.complete&&i.naturalWidth>0)')
        browser.evaluate('document.querySelector("[data-testid=stCheckbox] input").click()')
        browser.wait('document.body.innerText.includes("GEOMETRY_REVIEW_COMPLETE_True")', timeout=60)
        after = before + sum(len(visible_assets(q, solution=True)) for q in rows)
        browser.wait('document.querySelectorAll("[data-testid=stImage] img").length===' + str(after))
        errors = browser.evaluate('Array.from(document.querySelectorAll(".katex-error")).map(e=>({text:e.innerText,title:e.title}))')
        assert not errors, errors
        assert browser.evaluate('!document.body.innerText.includes("[公式需要修复]")')
        browser.wait('Array.from(document.querySelectorAll("[data-testid=stImage] img")).every(i=>i.complete&&i.naturalWidth>0)', timeout=30)
        result = dict(result='PASS', recovered_questions=len(rows), question_images=before,
                      solution_images=after-before, total_images=after,
                      rendered_math=browser.evaluate('document.querySelectorAll(".katex").length'),
                      katex_errors=errors, solution_images_before=0, database_writes=False, folder=str(folder))
        (ROOT / 'reports/geometry_v1_1e_assets_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return result
    finally:
        if browser:
            browser.ws.close()
        if edge:
            edge.terminate()
            edge.wait(timeout=15)
        server.terminate()
        server.wait(timeout=15)
        server_log.close()
        edge_log.close()


if __name__ == '__main__':
    smoke()
