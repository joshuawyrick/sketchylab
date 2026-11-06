"""Hats from the photo: the theme setting is added after the prompt in builder tests, shown in Full prompt, told to the writer,
baked into the booth export (not Pet alone), and adds nothing when not set. Run: LTEST=test/hats.py bash test/run.sh"""
import asyncio, io, json, os, sys, zipfile, urllib.request
from playwright.async_api import async_playwright
B = 'http://localhost:3457'; FACE = os.environ.get('FACE', 'test/face.png'); fails = []
def check(ok, what):
    print(('ok   ' if ok else 'FAIL ') + what)
    if not ok: fails.append(what)
def api(path, body=None, raw=False):
    r = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method='POST' if body is not None else 'GET', headers={'x-admin-token': 'pw', 'content-type': 'application/json'})
    d = urllib.request.urlopen(r).read(); return d if raw else json.loads(d)
async def until(pg, js, secs=40):
    for _ in range(secs * 4):
        if await pg.evaluate(js): return True
        await pg.wait_for_timeout(250)
    return False
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(); pg = await (await br.new_context(viewport={'width': 1400, 'height': 1100})).new_page(); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('dialog', lambda d: asyncio.ensure_future(d.accept('Cowboys') if d.type == 'prompt' else d.accept()))
        await pg.goto(B + '/'); await pg.fill('#pw', 'pw'); await pg.click('#loginBtn'); await pg.wait_for_timeout(1500)
        await pg.click('#newTheme'); await pg.wait_for_timeout(1200); slug = await pg.input_value('#bdTheme')
        check(await pg.input_value('#bdHat') == '', 'a new theme starts at Not set')
        await pg.fill('#bdFoundText', 'FOUNDATION RULES.'); await pg.click('#bdFoundSave'); await pg.wait_for_timeout(400)
        await pg.fill('#bdDesc', 'Cowboys and cowgirls in big cowboy hats.'); await pg.press('#bdDesc', 'Tab'); await pg.wait_for_timeout(600)
        await pg.select_option('#bdHat', 'theme'); await pg.wait_for_timeout(600)
        t = [x for x in api('/api/state')['themes'] if x['slug'] == slug][0]; check(t['settings'].get('headwear') == 'theme', 'setting saved on the theme')
        await pg.set_input_files('#faceIn', [FACE]); await pg.wait_for_timeout(1500)
        for v in ['1-male', 'pet-only']: await pg.click(f'#bdGrid [data-slot="{v}"]'); await pg.wait_for_timeout(120)
        await pg.evaluate("() => document.querySelectorAll('#bdModels input').forEach(i => i.checked = i.value === 'openai-direct/gpt-image-2')")
        n0 = len(open('test/fakeor.log').read().splitlines())
        for v in ['1-male', 'pet-only']: await pg.click(f'#bdGrid [data-write="{v}"]'); await pg.wait_for_timeout(300)
        for _ in range(120):
            rs = [r for r in api(f'/api/runs?theme={slug}')['runs'] if r['kind'] == 'build']
            if len(rs) >= 2 and all(r['status'] == 'done' for r in rs): break
            await pg.wait_for_timeout(500)
        by = {r['variant']: r for r in rs}
        m = by['1-male']; check(m['fullPrompt'].startswith('FOUNDATION RULES.') and m['fullPrompt'].endswith('\n\n' + m['rule']) and 'HATS AND GLASSES FROM THE PHOTO: Leave out any hat' in m['rule'], 'Single male test: foundation + prompt + the hats rule at the end')
        check('Glasses worn over the eyes always stay' in m['rule'], 'the rule keeps glasses on the face')
        check(m['prompt'] and 'HATS AND GLASSES' not in m['prompt'], 'the kept prompt itself stays clean (rule is not baked in twice)')
        check('HATS AND GLASSES' not in by['pet-only']['fullPrompt'] and not by['pet-only'].get('rule'), 'Pet alone gets no hats rule')
        log = open('test/fakeor.log').read().splitlines()[n0:]; w = [l for l in log if 'openai write' in l]
        check(any(l.startswith('writer hats-note COMBINATION: Single male') for l in log) and not any('hats-note COMBINATION: Pet alone' in l for l in log), 'the prompt writer is told the rule is added (not for Pet alone)')
        await pg.click(f'.lab[data-id="{m["id"]}"] [data-full]'); await pg.wait_for_timeout(300)
        secs = await pg.eval_on_selector_all('#fpText .sec', 'els => els.map(e => e.textContent)'); pre = await pg.eval_on_selector_all('#fpText pre', 'els => els.map(e => e.textContent)')
        check(secs[-1] == 'Hats & glasses rule (theme setting)' and secs[0].startswith('Foundation') and len(secs) == 3 and pre[0] + '\n\n' + pre[1] + '\n\n' + pre[2] == m['fullPrompt'], f'Full prompt shows foundation, prompt and the rule {secs}')
        await pg.screenshot(path=os.environ.get('SHOT', '/tmp/hats.png')); await pg.keyboard.press('Escape')
        # keep both, export for the booth
        for r in (m, by['pet-only']): await pg.click(f'#bdGrid [data-keep="{r["id"]}"]'); await pg.wait_for_timeout(900)
        z = zipfile.ZipFile(io.BytesIO(api(f'/api/themes/export?slug={slug}&bake=1', raw=True))); f = {n.split('/')[-1]: z.read(n).decode() for n in z.namelist() if n.endswith(('.md', '.txt'))}
        check(f['single-male.md'].startswith('FOUNDATION RULES.') and f['single-male.md'].endswith(m['rule']) and f['single-male.md'].count('HATS AND GLASSES FROM THE PHOTO') == 1, 'export: single-male.md = foundation + prompt + rule, once')
        check('HATS AND GLASSES' not in f['pet-alone.md'], 'export: pet-alone.md has no hats rule')
        check('headwear: theme' in f.get('theme.txt', ''), 'export: theme.txt records the setting')
        # Keep what they're wearing / No hat / Not set
        for val, needle in (('keep', 'exactly as it is'), ('none', 'add no hat for the theme')):
            await pg.select_option('#bdHat', val); await pg.wait_for_timeout(500)
            z = zipfile.ZipFile(io.BytesIO(api(f'/api/themes/export?slug={slug}&bake=1', raw=True))); sm = [z.read(n).decode() for n in z.namelist() if n.endswith('single-male.md')][0]
            check(needle in sm and sm.count('HATS AND GLASSES FROM THE PHOTO') == 1, f'export with "{val}" uses that rule')
        await pg.select_option('#bdHat', ''); await pg.wait_for_timeout(500)
        t = [x for x in api('/api/state')['themes'] if x['slug'] == slug][0]; check('headwear' not in t['settings'], 'Not set removes the setting')
        z = zipfile.ZipFile(io.BytesIO(api(f'/api/themes/export?slug={slug}&bake=1', raw=True))); sm = [z.read(n).decode() for n in z.namelist() if n.endswith('single-male.md')][0]
        check('HATS AND GLASSES' not in sm and sm == 'FOUNDATION RULES.\n\n' + m['prompt'].strip(), 'Not set: the export is exactly foundation + prompt, as before')
        await pg.reload(); await pg.wait_for_timeout(1500); await pg.select_option('#bdTheme', slug); await pg.wait_for_timeout(800); check(await pg.input_value('#bdHat') == '', 'page shows Not set after a reload')
        check(not errs, f'no page errors {errs}'); await br.close()
    print('\nFAILED:' if fails else '\nALL PASSED', fails or ''); sys.exit(1 if fails else 0)
asyncio.run(main())
