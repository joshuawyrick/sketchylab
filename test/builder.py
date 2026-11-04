"""Theme builder end to end against the fake OpenRouter/OpenAI (test/fakeor.js):
new theme -> description -> write all 8 -> images -> keep two -> retry the rest with a note -> edit & test -> un-keep -> export zip.
Also checks the consolidated tabs (Prompt test still runs) and that the export is booth-safe."""
import asyncio, json, os, io, sys, zipfile, urllib.request
from playwright.async_api import async_playwright
B = 'http://localhost:3457'; FACE = os.environ.get('FACE', 'test/face.png'); SHOT = os.environ.get('SHOT', '/tmp/builder.png')
def api(path, body=None, method=None, raw=False):
    r = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method=method or ('POST' if body is not None else 'GET'), headers={'x-admin-token': 'pw', 'content-type': 'application/json'})
    d = urllib.request.urlopen(r).read(); return d if raw else json.loads(d)
async def until(pg, js, secs=40):
    for _ in range(secs * 4):
        if await pg.evaluate(js): return True
        await pg.wait_for_timeout(250)
    return False
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(); pg = await (await br.new_context(viewport={'width': 1400, 'height': 1100})).new_page(); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('dialog', lambda d: asyncio.ensure_future(d.accept(d.default_value or 'Space Pirates') if d.type == 'prompt' else d.accept()))
        await pg.goto(B + '/'); await pg.fill('#pw', 'pw'); await pg.click('#loginBtn'); await pg.wait_for_timeout(1500)
        print('tabs:', [await b.text_content() for b in await pg.query_selector_all('#nav button[data-t]')])
        # foundation text so prompts get one
        await pg.click('#nav [data-t=found]'); await pg.fill('#fList .prompt[data-i="0"] .fText', 'SIMPLE FACE RULES: realistic line art, single line thickness.'); await pg.click('#fSave'); await pg.wait_for_timeout(700)
        await pg.click('#nav [data-t=build]'); await pg.wait_for_timeout(300)
        print('empty state shown:', await pg.is_visible('#bdNone'))
        await pg.click('#newTheme'); await pg.wait_for_timeout(1200)
        print('theme selected:', await pg.input_value('#bdTheme'), '| body shown:', await pg.is_visible('#bdBody'))
        await pg.fill('#bdDesc', 'Space pirates: captain coat over a flight suit, ray-gun holster, robot parrot.'); await pg.dispatch_event('#bdDesc', 'change'); await pg.wait_for_timeout(400)
        await pg.click('#bdRating button[data-v=adult]'); await pg.wait_for_timeout(300)
        await pg.set_input_files('#faceIn', [FACE]); await pg.wait_for_timeout(1500)
        for v in ['1-male', '1-female', '2-male-female', 'pet-female']: await pg.click(f'#bdGrid [data-slot="{v}"]'); await pg.wait_for_timeout(120)
        # one OpenAI-direct model + one OpenRouter model (non-OpenAI, so the export must leave it out of theme.txt)
        await pg.evaluate("() => document.querySelectorAll('#bdModels input').forEach(i => i.checked = ['openai-direct/gpt-image-2', 'black-forest-labs/flux.2-pro'].includes(i.value))")
        print('models ticked:', await pg.evaluate("() => Array.from(document.querySelectorAll('#bdModels input:checked')).map(i => i.value)"))
        await pg.click('#bdWriteAll'); await pg.wait_for_timeout(500)
        print('msg:', await pg.text_content('#bdMsg'))
        ok = await until(pg, "() => document.querySelectorAll('#bdGrid .draft .dp').length >= 8 && !document.querySelector('#bdGrid .draft .spin')")
        b = api('/api/builder/space-pirates')['builder']
        print('drafts written:', ok, len(b['drafts']), '| statuses:', sorted(set(d['status'] for d in b['drafts'])), '| sample:', b['drafts'][0]['prompt'][:70])
        print('markdown stripped:', not any('##' in d['prompt'] or '**' in d['prompt'] for d in b['drafts']))
        await until(pg, "() => document.querySelectorAll('#bdGrid .lab img').length >= 8 && !document.querySelector('#bdGrid .lab .wait')", 60)
        runs = [r for r in api('/api/runs')['runs'] if r['kind'] == 'build']
        print('images:', len(runs), '(4 faces x 2 models expected) | full prompt starts with foundation:', all(r['fullPrompt'].startswith('SIMPLE FACE RULES') for r in runs), '| adult -> moderation low:', all(r.get('moderation') == 'low' for r in runs))
        # keep single female (OpenAI) and single male (flux)
        sf = [r for r in runs if r['variant'] == '1-female' and r['model'] == 'openai-direct/gpt-image-2'][0]; sm = [r for r in runs if r['variant'] == '1-male' and r['model'] == 'black-forest-labs/flux.2-pro'][0]
        for r in (sf, sm): await pg.click(f'#bdGrid [data-keep="{r["id"]}"]'); await pg.wait_for_timeout(1300)
        t = [x for x in api('/api/state')['themes'] if x['slug'] == 'space-pirates'][0]
        print('kept:', [v for v in t['prompts'] if t['prompts'][v].strip()], '| progress:', await pg.text_content('#bdProgress'), '| thumbnail made:', t['hasThumb'])
        # retry the rest with a note on two-females... (no face there, so writes only) and on female+pet (has a face)
        await pg.fill('#bdGrid .bdNote[data-v="pet-female"]', 'make the parrot bigger')
        n0 = len(api('/api/builder/space-pirates')['builder']['drafts'])
        await pg.click('#bdWriteAll'); await pg.wait_for_timeout(600)
        await until(pg, "() => !document.querySelector('#bdGrid .draft .spin')")
        b = api('/api/builder/space-pirates')['builder']; new = b['drafts'][n0:]
        print('retry wrote', len(new), 'drafts for', sorted(set(d['variant'] for d in new)), '(kept ones skipped) | note used:', any('parrot bigger' in d['prompt'] for d in new if d['variant'] == 'pet-female'))
        # writer must have seen the kept prompts + previous attempt (check the fake log)
        log = open('test/fakeor.log').read(); print('writer calls in log:', log.count('openai write'))
        # edit & test a draft
        d = [x for x in new if x['variant'] == '2-male-female'][0]
        await pg.click(f'#bdGrid [data-dedit="{d["id"]}"]'); await pg.wait_for_timeout(200)
        await pg.fill(f'#bdGrid .dText[data-d="{d["id"]}"]', 'My own edited version of the couple prompt.'); await pg.click(f'#bdGrid [data-dsave="{d["id"]}"]'); await pg.wait_for_timeout(1200)
        b = api('/api/builder/space-pirates')['builder']; ed = [x for x in b['drafts'] if x.get('edited')]
        print('edited draft saved:', len(ed) == 1 and ed[0]['prompt'].startswith('My own'), '| its runs:', len(ed[0].get('runs', [])) if ed else 0)
        await until(pg, "() => !document.querySelector('#bdGrid .lab .wait')", 60)
        # un-keep single male
        await pg.click('#bdGrid [data-unkeep="1-male"]'); await pg.wait_for_timeout(1200)
        t = [x for x in api('/api/state')['themes'] if x['slug'] == 'space-pirates'][0]; print('after un-keep:', [v for v in t['prompts'] if t['prompts'][v].strip()])
        # keep the edited couple prompt
        er = [r for r in api('/api/runs')['runs'] if r.get('draft') == ed[0]['id'] and r['status'] == 'done'][0]
        await pg.click(f'#bdGrid [data-keep="{er["id"]}"]'); await pg.wait_for_timeout(1300)
        await pg.screenshot(path=SHOT, full_page=True)
        # export
        z = zipfile.ZipFile(io.BytesIO(api('/api/themes/export?slug=space-pirates&bake=1', raw=True)))
        names = sorted(z.namelist()); print('zip:', names)
        sf_txt = z.read('Space Pirates/single-female.md').decode(); print('single-female baked with foundation:', sf_txt.startswith('SIMPLE FACE RULES'), '| no markdown:', '##' not in sf_txt)
        tt = z.read('Space Pirates/theme.txt').decode(); print('theme.txt:\n' + tt)
        # consolidated Prompt test still works
        await pg.click('#nav [data-t=matrix]'); await pg.wait_for_timeout(300)
        print('prompt test title:', (await pg.text_content('#tab-matrix h2'))[:12], '| face picker has faces:', len(await pg.query_selector_all('#mxFaces .face')))
        await pg.click('#mxFaces .face img'); await pg.fill('#mxPrompts .mxText', 'pirate test'); await pg.evaluate("() => document.querySelectorAll('#mxModels input').forEach(i => i.checked = i.value === 'openai-direct/gpt-image-2')")
        await pg.click('#mxRun'); await pg.wait_for_timeout(2500); print('prompt test results:', len(await pg.query_selector_all('#mxGrid .lab')))
        print('ERRORS:', errs or 'none'); await br.close()
asyncio.run(main())
