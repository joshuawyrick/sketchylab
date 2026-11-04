#!/usr/bin/env python3
"""Preset test page, end to end with a fake arm. Run the server first:
   DATA_DIR=/tmp/lab-test ADMIN_PASSWORD=pw PORT=3461 node server/index.js
   python3 test/presets.py [folder for screenshots]"""
import asyncio, json, re, sys, os, tempfile
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw
OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
B = 'http://localhost:3461'
FAKE = """
  Object.defineProperty(navigator, 'serial', { configurable: true, value: { addEventListener: () => {}, getPorts: async () => [], requestPort: async () => ({
    open: async () => {}, close: async () => {}, addEventListener: () => {},
    readable: new ReadableStream({ start(c) { window.__push = t => c.enqueue(new TextEncoder().encode(t)); } }),
    writable: new WritableStream({ write(chunk) { const line = new TextDecoder().decode(chunk).trim(); (window.__lines = window.__lines || []).push(line); setTimeout(() => { if (/^M114/.test(line)) window.__push('X:0.00 Y:300.00 Z:1.20 E:0.00\\r\\nok\\r\\n'); else if (/^M2010/.test(line)) window.__push('V2.4.4\\r\\nok\\r\\n'); else window.__push('ok\\r\\n'); }, 0); } })
  }) } });"""
HIDDEN = ['spDraw','zoneSpeed','spTravel','spZ','acc','accT','jerk','fastTravel','inflight','imgThr','imgRes','imgSpeck','penW','fillX','imgSmooth','imgPrune','optOrder','optJoin','optSimp','optMin','optMinDetail','optSimpDetail','zDown','zLift','zSafe','szW','posX','margin','paperX','paperY','jogSpeed','btnGen','btnDl','btnQNext']

def picture(path):
    im = Image.new('RGB', (1024, 1536), 'white'); d = ImageDraw.Draw(im)
    d.ellipse((260, 180, 760, 860), outline='black', width=5)
    for x, y in ((390, 430), (630, 430)):
        d.ellipse((x-55, y-30, x+55, y+30), outline='black', width=4); d.ellipse((x-22, y-22, x+22, y+22), outline='black', width=4); d.ellipse((x-7, y-7, x+7, y+7), fill='black')
    d.polygon([(320, 350), (450, 335), (450, 360), (320, 372)], fill='black'); d.polygon([(570, 335), (700, 350), (700, 372), (570, 360)], fill='black')
    d.line((510, 450, 480, 590, 530, 600), fill='black', width=4); d.arc((390, 610, 630, 740), 15, 165, fill='black', width=5)
    for i in range(70): d.line((260+i*7, 190+abs(35-i)*3, 240+i*8, 70+(i%9)*6), fill='black', width=3)
    for i in range(40): d.line((300+i*5, 900, 240+i*14, 1400), fill='black', width=3)
    for i in range(50): d.ellipse((120+i*16, 1450, 123+i*16, 1453), fill='black')
    im.save(path)

async def main():
    pic = os.path.join(OUT, 'face.png'); picture(pic); fails = []
    def check(ok, what):
        print(('ok   ' if ok else 'FAIL ') + what)
        if not ok: fails.append(what)
    async with async_playwright() as p:
        b = await p.chromium.launch(); c = await b.new_context(viewport={'width': 1440, 'height': 1000}); await c.grant_permissions(['clipboard-read', 'clipboard-write'], origin=B)
        s = await c.new_page(); await s.add_init_script(FAKE); errs, bad = [], []
        s.on('pageerror', lambda e: errs.append(str(e))); s.on('response', lambda r: bad.append((r.status, r.url.replace(B, ''))) if r.status >= 400 else None); s.on('dialog', lambda d: asyncio.ensure_future(d.accept()))
        await s.goto(B + '/studio/'); await s.wait_for_timeout(600)
        check(await s.is_visible('#ptLogin'), 'asks for the Lab password')
        await s.fill('#ptPw', 'nope'); await s.click('#ptGo'); await s.wait_for_timeout(300); check('Wrong' in await s.inner_text('#ptLoginErr'), 'wrong password refused')
        bad.clear(); await s.fill('#ptPw', 'pw'); await s.click('#ptGo'); await s.wait_for_selector('.ptRow')
        check(await s.locator('.ptRow').count() == 10, '10 presets shown')
        vis = [i for i in HIDDEN if await s.is_visible('#' + i)]; check(not vis, f'no speed or drawing settings visible {vis}')
        await s.set_input_files('#file', pic); await s.wait_for_timeout(5000)
        await s.click('#btnConnect'); await s.wait_for_timeout(800); check('connected' in await s.inner_text('#status'), 'fake arm connected')
        check(await s.is_disabled('#btnStart'), 'Start stays off until a preset is picked')
        names = await s.locator('.ptPick').all_inner_texts(); seen, table = {}, []
        for i in range(10):
            await s.evaluate('window.__lines = []'); await s.locator('.ptPick').nth(i).click()
            await s.wait_for_function('!document.getElementById("ptList").classList.contains("locked")', timeout=120000); await s.wait_for_timeout(300)
            check(await s.is_enabled('#btnStart'), f'preset {i+1}: Start available')
            if i == 2: await s.screenshot(path=os.path.join(OUT, 'test-page.png')); check('Ready to draw #3' in await s.inner_text('#progTxt'), 'old done message clears when a new preset is picked')
            await s.evaluate('window.__lines = []'); await s.click('#btnStart'); await s.wait_for_timeout(100)
            check(await s.locator('.ptDel').first.evaluate('e => getComputedStyle(e).pointerEvents') == 'none', f'preset {i+1}: presets locked while drawing')
            await s.wait_for_function('document.getElementById("ptMsg").textContent.includes("finished in")', timeout=180000)
            lines = await s.evaluate('window.__lines'); g = [l for l in lines if l[:2] in ('G0', 'G1', 'M2')]
            fs = [float(m) for l in lines for m in re.findall(r' F([\d.]+)', l)]; m204 = next(l for l in lines if l.startswith('M204')); m205 = next(l for l in lines if l.startswith('M205'))
            acc = [float(x) for x in re.findall(r'[PT](\d+)', m204)]
            check(max(fs) <= 18000 and max(acc) <= 3000, f'preset {i+1}: inside firmware limits')
            check(not any(l.startswith('M2001') for l in lines), f'preset {i+1}: straight-line travel only')
            print('     ', names[i].split('\n')[0], '|', m204.split(';')[0], '|', m205.split(';')[0], '| max F', int(max(fs)), '| lines', len(lines), '|', (await s.locator('.ptRow').nth(i).locator('small').nth(1).inner_text()))
            seen['\n'.join(lines)] = i; await s.evaluate("document.getElementById('ptMsg').textContent=''")
        check(len(seen) == 10, 'all 10 send different G-code to the arm')
        st = await s.evaluate("fetch('/api/plotter-test',{headers:{'x-admin-token':'pw'}}).then(r=>r.json())"); check(all(len(p['runs']) == 1 for p in st['presets']), 'every drawing time was saved')
        # rate, note, delete, reload
        await s.locator('.ptRow').nth(4).locator('.ptStar').nth(3).click(); await s.wait_for_timeout(300)
        await s.locator('.ptPick').nth(4).click(); await s.wait_for_function('!document.getElementById("ptList").classList.contains("locked")', timeout=120000)
        await s.fill('.ptNote', 'great eyes'); await s.press('.ptNote', 'Tab'); await s.wait_for_timeout(300)
        await s.locator('.ptRow').nth(5).locator('.ptDel').click(); await s.wait_for_timeout(300); await s.locator('.ptRow').nth(0).locator('.ptDel').click(); await s.wait_for_timeout(400)
        check(await s.locator('.ptRow').count() == 8, 'deleted presets disappear')
        await s.reload(); await s.wait_for_selector('.ptRow'); await s.wait_for_timeout(5000)
        check(await s.locator('.ptRow').count() == 8, 'deletes survive a reload'); check('face.png' in await s.inner_text('#fileInfo'), 'test picture still there after a reload')
        on = await s.locator('.ptRow.on .ptPick').inner_text(); check('#5' in on, 'selected preset remembered'); check(await s.input_value('.ptNote') == 'great eyes', 'note saved')
        check(await s.locator('.ptRow.on .ptStar.on').count() == 4, 'rating saved')
        # results + new batch
        await s.click('#ptCopy'); await s.wait_for_timeout(300); r = json.loads(await s.evaluate('navigator.clipboard.readText()'))
        check(len(r['kept']) == 8 and sorted(d['n'] for d in r['deleted']) == [1, 6] and r['deleted'][0]['speed']['spDraw'] == 2500, 'results include kept and deleted presets with their settings')
        batch = [{'name': 'Copy of a deleted one', 'blurb': 'x', 'speed': r['deleted'][0]['speed'], 'conv': r['deleted'][0]['conv']}, {'name': 'Copy of a kept one', 'speed': r['kept'][0]['speed'], 'conv': r['kept'][0]['conv']}, {'name': 'Too fast', 'speed': {'spDraw': 99999, 'acc': 99999, 'zLift': 0}, 'conv': {'imgDots': False}}]
        await s.click('#ptAddBtn'); await s.fill('#ptText', 'not json'); await s.click('#ptAddGo'); check('not a complete' in await s.inner_text('#ptMsg'), 'bad paste explained')
        await s.fill('#ptText', json.dumps(batch)); await s.click('#ptAddGo'); await s.wait_for_timeout(400); msg = await s.inner_text('#ptMsg'); print('     ', msg)
        check('Added 1' in msg and 'Copy of a deleted one' in msg and 'Copy of a kept one' in msg, 'settings already tried are refused')
        st = await s.evaluate("fetch('/api/plotter-test',{headers:{'x-admin-token':'pw'}}).then(r=>r.json())"); new = st['presets'][-1]
        check(new['n'] == 11 and new['speed']['spDraw'] == 18000 and new['speed']['acc'] == 3000 and new['speed']['zLift'] == 2, 'new preset is #11 and clamped to safe limits')
        await s.click('section.closed > h2'); check(await s.is_visible('#console'), 'console opens when its title is clicked')
        await s.screenshot(path=os.path.join(OUT, 'test-page-after.png'))
        check(not errs, f'no page errors {errs}'); check(not bad, f'no failed requests {bad[:5]}')
        # Lab page still works alongside it
        l = await c.new_page(); await l.goto(B + '/'); await l.fill('#pw', 'pw'); await l.click('#loginBtn'); await l.wait_for_timeout(600); check(await l.is_visible('#tab-build'), 'Lab page still works')
        await l.click('#nav button[data-t=settings]'); await l.click('#sSave'); await l.wait_for_timeout(300)
        st2 = await s.evaluate("fetch('/api/plotter-test',{headers:{'x-admin-token':'pw'}}).then(r=>r.json())"); check(len(st2['presets']) == 11, 'saving Lab settings keeps the preset data')
        await b.close()
    print('\nFAILED:' if fails else '\nALL PASSED', fails or ''); sys.exit(1 if fails else 0)
asyncio.run(main())
