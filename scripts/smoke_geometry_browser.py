"""Headless real Streamlit acceptance on a SQLite backup, never production attempts."""
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import base64
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
from database.database import get_connection, get_approved_questions, record_attempt
from database.geometry import import_geometry
from database.taxonomy_migration import protected_snapshot
from database.training_sessions import save_session, get_latest_session
from database.diagnostic import load_latest
from services.geometry_review import read_rows
from services.diagnostic import start_diagnostic
from services.adaptive_training import start_training_session, end_training_session


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def smoke():
    folder = ROOT / 'tmp' / ('geometry_browser_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    folder.mkdir(parents=True)
    path = folder / 'browser.sqlite3'
    with closing(get_connection(ROOT / 'math_ai.db', read_only=True)) as source, closing(get_connection(path)) as target:
        original_before = protected_snapshot(source)
        source.backup(target)
    imported = import_geometry(path, read_rows(ROOT / 'data/question_bank/geometry_v1_1c/approved_ready.jsonl'))
    student = 'GEOMETRY-BROWSER-V1_1C'
    web, debug = free_port(), free_port()
    env = dict(os.environ)
    env.update(MATH_AI_DATABASE_PATH=str(path), ACTIVE_TAXONOMY_VERSION='function_v2')
    for key in ('OPENAI_API_KEY', 'DEEPSEEK_API_KEY', 'GEMINI_API_KEY'):
        env.pop(key, None)
    server_log = (folder / 'streamlit.log').open('w', encoding='utf-8')
    edge_log = (folder / 'edge.log').open('w', encoding='utf-8')
    # Same entry point and pages, with a deterministic synthetic default student.
    entry = ROOT / ('_browser_fixture_' + folder.name + '.py')
    entry.write_text((ROOT / 'app.py').read_text(encoding='utf-8').replace("value='S001'", f"value='{student}'"), encoding='utf-8')
    server = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(entry), '--server.headless=true',
                               f'--server.port={web}', '--browser.gatherUsageStats=false'], cwd=ROOT, env=env,
                              stdout=server_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    edge, browser = None, None
    results = []
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{web}/_stcore/health', timeout=1)
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Streamlit启动失败')
                time.sleep(.2)
        edge = subprocess.Popen(['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', '--headless=new',
                                  '--disable-gpu', '--no-first-run', '--disable-background-networking', '--disable-component-update',
                                  '--disable-sync', f'--remote-debugging-port={debug}', '--remote-allow-origins=*',
                                  '--user-data-dir=' + str(folder / 'edge_profile'), 'about:blank'],
                                 stdout=edge_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(100):
            try:
                tab = next(t for t in json.load(urllib.request.urlopen(f'http://127.0.0.1:{debug}/json', timeout=1)) if t.get('type') == 'page')
                break
            except (OSError, StopIteration):
                time.sleep(.2)
        browser = Browser(tab['webSocketDebuggerUrl'])
        browser.call('Page.enable')
        browser.call('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 1100, 'deviceScaleFactor': 1, 'mobile': False})
        browser.call('Page.navigate', {'url': f'http://127.0.0.1:{web}/'})
        browser.wait('document.body.innerText.includes("高中数学个性化学习系统")')
        browser.wait('document.querySelector("[data-testid=stSidebar] [data-testid=stTextInput] input").value===' + json.dumps(student))

        def navigate(label):
            expression = 'Array.from(document.querySelectorAll("a")).find(a=>a.innerText.trim()===' + json.dumps(label) + ')'
            browser.wait('!!(' + expression + ')')
            browser.evaluate('(' + expression + ').click()')
            time.sleep(.7)

        def topic(label):
            browser.wait('!!document.querySelector("[data-testid=stSidebar] [data-baseweb=select]")')
            browser.evaluate('document.querySelector("[data-testid=stSidebar] [data-baseweb=select] [role=combobox]").click()')
            option = 'Array.from(document.querySelectorAll("[role=option]")).find(e=>e.innerText.trim()===' + json.dumps(label) + ')'
            browser.wait('!!(' + option + ')')
            browser.evaluate('(' + option + ').click()')
            browser.wait('document.body.innerText.includes(' + json.dumps('当前专题：' + label) + ')')

        def audit_screen():
            body = browser.evaluate('document.body.innerText')
            assert not any(marker in body for marker in ['[图片待核]', '[公式待核]', '[公式需要修复]', 'GA-', 'GQ-', 'oMath']), body[-2000:]
            errors = browser.evaluate('Array.from(document.querySelectorAll(".katex-error")).map(e=>({text:e.innerText,title:e.title}))')
            assert not errors, errors
            assert not browser.evaluate('!!document.querySelector("[data-testid=stException]")'), body[-2000:]
            return {'katex_errors': errors, 'math_count': browser.evaluate('document.querySelectorAll(".katex").length')}

        def choose(q):
            kind = q['question_type']
            if kind == 'single_choice':
                browser.wait('document.querySelectorAll("[data-testid=stRadio] input[type=radio]").length===' + str(len(q['options'])))
                browser.evaluate(f'document.querySelectorAll("[data-testid=stRadio] input[type=radio]")[{list(q["options"]).index(q["answer"])}].click()')
            elif kind == 'multiple_choice':
                browser.wait('document.querySelectorAll("[data-testid=stCheckbox] input").length===' + str(len(q['options'])))
                for label in q['correct_answers']:
                    browser.evaluate(f'document.querySelectorAll("[data-testid=stCheckbox] input")[{list(q["options"]).index(label)}].click()')
                    time.sleep(.2)
            elif kind == 'fill_blank':
                browser.input('[data-testid=stMain] [data-testid=stTextInput] input', q['canonical_answer'])
            else:
                browser.input('[data-testid=stMain] textarea', '根据已知条件写出证明与计算过程。')
            time.sleep(.4)

        topic('立体几何与空间向量')
        navigate('首次诊断')
        browser.wait('document.body.innerText.includes("立体几何与空间向量知识诊断测评")')
        browser.click_text('开始诊断')
        browser.wait('document.body.innerText.includes("第 1 / 15 题")')
        for index in range(15):
            state = load_latest(student, path, taxonomy_version='geometry_v1')
            q = state['current_question']
            browser.wait('document.body.innerText.includes(' + json.dumps(f'第 {index+1} / 15 题') + ')')
            result = audit_screen()
            choose(q)
            browser.click_text('提交答案')
            browser.wait('document.body.innerText.includes(' + json.dumps('诊断完成' if index == 14 else f'第 {index+2} / 15 题') + ')')
            results.append({'diagnostic_index': index+1, 'question_id': q['id'], 'type': q['question_type'], **result})
            print('诊断完成题数：' + str(index+1), flush=True)
        diagnostic = load_latest(student, path, taxonomy_version='geometry_v1')
        assert diagnostic['diagnostic_completed']
        assert len(diagnostic['answers']) == 15
        # Exercise explicit image/type scenarios using the real training page.
        # Synthetic prerequisite evidence and selected sessions stay in the copy.
        pool = get_approved_questions(database_path=path, taxonomy_version='geometry_v1')
        for key in sorted({q['knowledge_point_id'] for q in pool}):
            seed = next((q for q in pool if q['knowledge_point_id'] == key and q['question_type'] == 'single_choice'), None)
            if seed:
                for _ in range(8):
                    record_attempt(student, seed['id'], seed['answer'], 1, 1, database_path=path, taxonomy_version='geometry_v1')
        selected = {
            'no_diagram_choice': next(q for q in pool if q['question_type'] == 'single_choice' and not q['diagram_required']),
            'diagram_choice': next(q for q in pool if q['question_type'] == 'single_choice' and q['diagram_required']),
            'fill_blank': next(q for q in pool if q['question_type'] == 'fill_blank'),
            'subjective': next(q for q in pool if q['question_type'] == 'subjective' and q.get('max_score')),
            'multi_diagram': next(q for q in pool if len([a for a in q['diagram_assets'] if a['role'] in {'question_diagram', 'option_image'}]) >= 2),
            'solution_only': next(q for q in pool if not q['diagram_required'] and any(a['role'] == 'solution_diagram' for a in q['diagram_assets'])),
        }
        scenarios = []
        for name, q in selected.items():
            previous = get_latest_session(student, path, taxonomy_version='geometry_v1')
            if previous and previous['status'] == 'active':
                end_training_session(student, previous['id'], database_path=path)
            state = start_training_session(student, taxonomy_version='geometry_v1', target_knowledge_point_id=q['knowledge_point_id'], database_path=path, lock_target=True)
            state.update(current_question=q, submitted=False, question_started_at=time.time(), selection_note='隔离网页验收', question_hint_count=0, question_retry_count=0)
            with closing(get_connection(path)) as connection, connection:
                connection.execute('INSERT INTO training_session_questions(session_id,question_id,sequence_no,difficulty) VALUES (?,?,?,?)', (state['id'], q['id'], 1, q['difficulty']))
                save_session(connection, state)
            navigate('开始训练')
            browser.wait('document.body.innerText.includes("提交答案")')
            time.sleep(.4)
            pre = audit_screen()
            captions = browser.evaluate('Array.from(document.querySelectorAll("[data-testid=stImage] figcaption")).map(e=>e.innerText)')
            assert '解析图' not in captions, (name, captions)
            expected = len([a for a in q['diagram_assets'] if a['role'] in {'question_diagram', 'option_image'}])
            browser.wait('document.querySelectorAll("[data-testid=stImage] img").length===' + str(expected))
            assert browser.evaluate('Array.from(document.querySelectorAll("[data-testid=stImage] img")).every(i=>i.complete&&i.naturalWidth>0)')
            choose(q)
            browser.click_text('提交答案')
            browser.wait('document.body.innerText.includes("答案解析")')
            post = audit_screen()
            expected_solution = len([a for a in q['diagram_assets'] if a['role'] == 'solution_diagram'])
            browser.wait('document.querySelectorAll("[data-testid=stImage] img").length===' + str(expected + expected_solution))
            screenshot = browser.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True})['data']
            (folder / (name + '.png')).write_bytes(base64.b64decode(screenshot))
            scenarios.append({'scenario': name, 'question_id': q['id'], 'question_images_before': expected,
                              'solution_images_before': 0, 'solution_images_after': expected_solution, 'pre': pre, 'post': post})
            print('图像场景通过：' + name, flush=True)
        navigate('首页')
        topic('函数')
        function_pages = []
        for label, expected in [('首次诊断', '函数知识诊断测评'), ('开始训练', '自适应函数训练'),
                                ('学习画像', '函数学习画像'), ('个性化推荐', '当前专题：函数'), ('AI 学习反馈', '专题：函数')]:
            navigate(label)
            browser.wait('document.body.innerText.includes(' + json.dumps(expected) + ')')
            audit_screen()
            if label == '首次诊断':
                browser.click_text('开始诊断')
                browser.wait('document.body.innerText.includes("第 1 / 18 题")')
                state = load_latest(student, path, taxonomy_version='function_v2')
                assert all(q['knowledge_point_id'].startswith('K') for q in state['pool'])
            if label == 'AI 学习反馈':
                browser.click_text('查看规则式学习反馈')
                browser.wait('document.body.innerText.includes("规则式学习反馈")')
            function_pages.append(label)
        with closing(get_connection(ROOT / 'math_ai.db', read_only=True)) as connection:
            assert protected_snapshot(connection) == original_before
        result = {'result': 'PASS', 'folder': str(folder), 'diagnostic_count': len(diagnostic['answers']),
                  'diagnostic_type_counts': dict(Counter(a['question_type'] for a in diagnostic['answers'])),
                  'diagnostic_knowledge_coverage': sorted({a['knowledge_point_id'] for a in diagnostic['answers']}),
                  'diagnostic_submissions': results, 'image_scenarios': scenarios, 'function_pages_passed': function_pages,
                  'production_attempts_unchanged': True, 'database': str(path)}
        (ROOT / 'reports/geometry_browser_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: result[k] for k in ['result', 'folder', 'diagnostic_count', 'diagnostic_type_counts', 'diagnostic_knowledge_coverage', 'function_pages_passed']}, ensure_ascii=False), flush=True)
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
        entry.unlink(missing_ok=True)


if __name__ == '__main__':
    smoke()
