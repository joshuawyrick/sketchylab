"""Master prompts per combination and Pet alone, against the fake OpenRouter/OpenAI (test/fakeor.js).
Run: LTEST=test/masters.py bash test/run.sh"""
import asyncio, io, json, os, re, urllib.request, urllib.error, zipfile
from playwright.async_api import async_playwright
B = 'http://localhost:3457'; FACE = os.environ.get('FACE', 'test/face.png'); SHOT = os.environ.get('SHOT', '/tmp/masters.png')
GENERAL, MALE, PET = 'GENERAL RULES line art.', 'MALE MASTER one man.', 'PET MASTER one animal, no people.'
fails = []
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
        pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('dialog', lambda d: asyncio.ensure_future(d.accept('Pirates') if d.type == 'prompt' else d.accept()))
        await pg.goto(B + '/'); await pg.fill('#pw', 'pw'); await pg.click('#loginBtn'); await pg.wait_for_timeout(1500)
        await pg.click('#newTheme'); await pg.wait_for_timeout(1200)
        await pg.click('#bdRating button[data-v=adult]'); await pg.wait_for_timeout(300)
        check('Pet alone' in await pg.inner_text('#bdGrid'), 'Pet alone is a combination in the Theme builder')
        check(await pg.locator('#bdGrid .bRow.bd').count() == 9, '9 combinations shown')
        check('no pet photo' in await pg.inner_text('#bdGrid .bRow[data-v="pet-only"]'), 'Pet alone asks for a pet photo')
        # the box follows "Used for"; switching with unsaved text saves it
        await pg.fill('#bdFoundText', GENERAL); await pg.click('#bdFoundSave'); await pg.wait_for_timeout(400)
        await pg.select_option('#bdFoundFor', 'pet-only'); await pg.wait_for_timeout(300)
        check(await pg.input_value('#bdFoundText') == '', 'a combination with no master starts empty')
        await pg.fill('#bdFoundText', PET); await pg.dispatch_event('#bdFoundText', 'input')
        await pg.select_option('#bdFoundFor', '1-male'); await pg.wait_for_timeout(500)
        await pg.fill('#bdFoundText', MALE); await pg.dispatch_event('#bdFoundText', 'input'); await pg.click('#bdFoundSave'); await pg.wait_for_timeout(500)
        f = next(x for x in api('/api/state')['settings']['foundations'] if x['id'] == 'normal')
        check(f['text'] == GENERAL and f['combos'] == {'pet-only': PET, '1-male': MALE}, 'general text and both masters saved separately')
        opts = await pg.locator('#bdFoundFor option').all_inner_texts(); check('● Pet alone' in opts and '● Single male' in opts and 'Single female' in opts, 'combinations with a master are marked')
        await pg.select_option('#bdFoundFor', ''); await pg.wait_for_timeout(300); check(await pg.input_value('#bdFoundText') == GENERAL, 'All combinations shows the general text')
        await pg.click('#bdGrid [data-master="pet-only"]'); await pg.wait_for_timeout(400); check(await pg.input_value('#bdFoundText') == PET, 'row link opens that combination\'s master')
        check('own master' in await pg.inner_text('#bdGrid .bRow[data-v="pet-only"]') and 'All combinations' in await pg.inner_text('#bdGrid .bRow[data-v="1-female"]'), 'rows say which master they use')
        await pg.select_option('#bdFoundFor', ''); await pg.wait_for_timeout(300)
        # generate and test three combinations
        await pg.set_input_files('#faceIn', [FACE]); await pg.wait_for_timeout(1500)
        for v in ['1-male', '1-female', 'pet-only']: await pg.click(f'#bdGrid [data-slot="{v}"]'); await pg.wait_for_timeout(120)
        await pg.evaluate("() => document.querySelectorAll('#bdModels input').forEach(i => i.checked = i.value === 'openai-direct/gpt-image-2')")
        for v in ['1-male', '1-female', 'pet-only']: await pg.click(f'#bdGrid [data-write="{v}"]'); await pg.wait_for_timeout(300)
        slug = await pg.input_value('#bdTheme')
        for _ in range(120):
            rs = [r for r in api(f'/api/runs?theme={slug}')['runs'] if r['kind'] == 'build']
            if len(rs) >= 3 and all(r['status'] == 'done' for r in rs): break
            await pg.wait_for_timeout(500)
        by = {r['variant']: r for r in rs}; check(set(by) == {'1-male', '1-female', 'pet-only'}, 'all three drew')
        check(by['1-male']['fullPrompt'].startswith(MALE) and GENERAL not in by['1-male']['fullPrompt'], 'Single male tests with its own master')
        check(by['pet-only']['fullPrompt'].startswith(PET) and GENERAL not in by['pet-only']['fullPrompt'], 'Pet alone tests with its own master')
        check(by['1-female']['fullPrompt'].startswith(GENERAL), 'Single female falls back to All combinations')
        check(by['pet-only']['foundation'] == 'Normal · Pet alone master' and by['1-female']['foundation'] == 'Normal', 'results are labeled with the master used')
        check(not by['pet-only'].get('moderation') and by['1-male'].get('moderation') == 'low', 'Pet alone keeps standard moderation in an adult theme')
        log = open('test/fakeor.log').read(); pet = [l for l in log.splitlines() if 'COMBINATION: Pet alone' in l]; man = [l for l in log.splitlines() if 'COMBINATION: Single male' in l]
        check(pet and 'AUDIENCE: family' in pet[0] and PET in pet[0], 'prompt writer gets family audience and the pet master'); check(man and 'AUDIENCE: adult' in man[0] and MALE in man[0], 'an adult theme stays adult for people')
        # prompt test
        fid = 'normal'; run = lambda v: api('/api/test/matrix', {'face': None, 'variant': v, 'foundations': [fid, 'none'], 'prompts': [{'label': 'A', 'text': 'THE PROMPT'}], 'models': ['openai-direct/gpt-image-2']})['runs']
        rv = run('pet-only'); check(rv[0]['fullPrompt'] == PET + '\n\nTHE PROMPT' and rv[1]['fullPrompt'] == 'THE PROMPT', 'Prompt test uses the master for the picked combination')
        rv = run(None); check(rv[0]['fullPrompt'] == GENERAL + '\n\nTHE PROMPT', 'Prompt test with no combination uses All combinations')
        await pg.click('#nav [data-t=matrix]'); await pg.wait_for_timeout(300); await pg.select_option('#mxVar', 'pet-only'); await pg.wait_for_timeout(300); check('Pet alone master' in await pg.inner_text('#mxFound'), 'Prompt test shows which master is in use')
        # foundations tab keeps and edits masters
        await pg.click('#nav [data-t=found]'); await pg.wait_for_timeout(300); d = pg.locator('#fList .prompt').filter(has=pg.locator('.fName')).first
        await d.locator('details summary').click(); check(await d.locator('.fCombo[data-v="pet-only"]').input_value() == PET, 'Foundations tab shows the masters')
        await d.locator('.fCombo[data-v="2-male-male"]').fill('TWO MEN MASTER'); await d.locator('.fCombo[data-v="1-male"]').fill(''); await pg.click('#fSave'); await pg.wait_for_timeout(500); await pg.screenshot(path=SHOT, full_page=True)
        f = next(x for x in api('/api/state')['settings']['foundations'] if x['id'] == 'normal'); check(f['combos'] == {'2-male-male': 'TWO MEN MASTER', 'pet-only': PET} and f['text'] == GENERAL, 'Foundations tab saves; emptied master is removed')
        # export and re-import
        kept = next(r for r in rs if r['variant'] == 'pet-only'); api(f'/api/builder/{slug}/keep', {'runId': kept['id']})
        z = zipfile.ZipFile(io.BytesIO(api(f'/api/themes/export?theme={slug}&bake=1', raw=True))); names = z.namelist(); pf = [n for n in names if n.endswith('pet-alone.md')]
        check(pf and z.read(pf[0]).decode().startswith(PET), 'export bakes the master into pet-alone.md')
        # a zip of prompt writers: one foundation per folder, each file goes to its combination
        buf = io.BytesIO(); zw = zipfile.ZipFile(buf, 'w')
        for head in ('Normal_Head', 'Big_Head'):
            zw.writestr(f'Kit_v9.9/{head}/README.md', 'read me')
            for fn in ('single-male', 'single-female', 'single-pet'): zw.writestr(f'Kit_v9.9/{head}/{fn}.md', f'GENERATOR {head} {fn}\nTHEME: [INSERT THEME]')
        zw.close(); zp = '/tmp/kit.zip'; open(zp, 'wb').write(buf.getvalue())
        await pg.click('#nav [data-t=found]'); await pg.wait_for_timeout(200); await pg.set_input_files('#fImportIn', zp); await pg.wait_for_timeout(1000)
        fs = {f['id']: f for f in api('/api/state')['settings']['foundations']}; n = fs.get('normal-head-v9-9'); check(n and fs.get('big-head-v9-9') and set(n['combos']) == {'1-male', '1-female', 'pet-only'} and 'single-pet' in n['combos']['pet-only'], 'zip makes two foundations with files on the right combinations')
        check(fs['normal']['text'] == GENERAL and fs['normal']['combos']['pet-only'] == PET, 'import leaves existing foundations alone')
        await pg.click('#nav [data-t=build]'); await pg.wait_for_timeout(300); await pg.select_option('#bdFound', 'big-head-v9-9'); await pg.wait_for_timeout(600)
        check(await pg.locator('#bdHead button.on').get_attribute('data-v') == 'bighead', 'picking a Big Head foundation sets the head style')
        check('prompt writer' in await pg.inner_text('#bdGrid .bRow[data-v="pet-only"]'), 'rows show the prompt writer')
        await pg.click('#bdHead button[data-v=normal]'); await pg.wait_for_timeout(500); check(await pg.input_value('#bdFound') == 'normal-head-v9-9', 'head style switch stays in the same set')
        await pg.fill('#bdDesc', 'Space pirates with cutlasses'); await pg.dispatch_event('#bdDesc', 'change'); await pg.wait_for_timeout(300)
        before = len(open('test/fakeor.log').read().splitlines())
        for v in ['1-male', 'pet-only']: await pg.click(f'#bdGrid [data-write="{v}"]'); await pg.wait_for_timeout(300)
        for _ in range(120):
            rs2 = [r for r in api(f'/api/runs?theme={slug}')['runs'] if r['kind'] == 'build' and 'writer' in (r.get('foundation') or '')]
            if len(rs2) >= 2 and all(r['status'] == 'done' for r in rs2): break
            await pg.wait_for_timeout(500)
        wr = {r['variant']: r for r in rs2}; check(set(wr) == {'1-male', 'pet-only'}, 'prompt writers produced images')
        check('GENERATOR' not in wr['1-male']['fullPrompt'] and 'INSERT THEME' not in wr['1-male']['fullPrompt'] and wr['1-male']['fullPrompt'] == wr['1-male']['prompt'], 'image model gets only the finished prompt')
        check(wr['1-male']['foundation'] == 'Normal Head v9.9 · Single male writer', 'results name the writer')
        log = [l for l in open('test/fakeor.log').read().splitlines()[before:] if 'SYS[GENERATOR' in l]; lm = next((l for l in log if 'single-male' in l), ''); lp = next((l for l in log if 'single-pet' in l), '')
        check('Normal_Head single-male' in lm and 'THEME: Pirates — Space pirates with cutlasses' in lm and 'confirmed adult' in lm, 'text AI gets the right file, the filled-in theme and the 18+ audience')
        check('Normal_Head single-pet' in lp and 'THEME: Pirates ##' in lp and 'cutlasses' not in lp and 'never sexy' in lp, 'an adult theme stays out of the pet writer')
        try: api('/api/test/matrix', {'variant': '1-male', 'foundations': ['normal-head-v9-9'], 'prompts': [{'label': 'A', 'text': 'X'}], 'models': ['openai-direct/gpt-image-2']}); check(False, 'Prompt test refuses a prompt writer')
        except urllib.error.HTTPError as e: check(e.code == 400 and 'Theme builder' in e.read().decode(), 'Prompt test explains a prompt writer belongs in the Theme builder')
        await pg.click('#nav [data-t=matrix]'); await pg.wait_for_timeout(300); await pg.select_option('#mxVar', '1-male'); await pg.wait_for_timeout(300); check('writes prompts' in await pg.inner_text('#mxFound'), 'Prompt test marks prompt writers')
        check(not errs, f'no page errors {errs}')
        await br.close()
    print('\nFAILED:' if fails else '\nALL PASSED', fails or '')
asyncio.run(main())
