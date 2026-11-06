"""Theme builder end to end against the fake OpenRouter/OpenAI (test/fakeor.js):
new theme -> description -> write all 9 -> images -> keep two -> retry the rest with a note -> edit & test -> un-keep -> export zip.
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
        br = await p.chromium.launch(); ctx = await br.new_context(viewport={'width': 1400, 'height': 1100}); await ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=B); pg = await ctx.new_page(); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e))); ANS = ['Space Pirates']; pg.on('dialog', lambda d: asyncio.ensure_future(d.accept(ANS[0]) if d.type == 'prompt' else d.accept()))
        await pg.goto(B + '/'); await pg.fill('#pw', 'pw'); await pg.click('#loginBtn'); await pg.wait_for_timeout(1500)
        print('tabs:', [await b.text_content() for b in await pg.query_selector_all('#nav button[data-t]')])
        # foundation text so prompts get one
        await pg.click('#nav [data-t=build]'); await pg.wait_for_timeout(300)
        print('empty state shown:', await pg.is_visible('#bdNone'))
        await pg.click('#newTheme'); await pg.wait_for_timeout(1200)
        print('theme selected:', await pg.input_value('#bdTheme'), '| body shown:', await pg.is_visible('#bdBody'))
        print('foundation box shows:', await pg.input_value('#bdFound'), '| editable:', await pg.is_enabled('#bdFoundText'))
        await pg.fill('#bdFoundText', 'SIMPLE FACE RULES: realistic line art, single line thickness.')  # not saved by hand: Generate must save it
        print('buttons:', (await pg.text_content('#bdWriteAll')).strip(), '|', (await pg.text_content('#bdGrid [data-write="1-male"]')).strip())
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
        print('foundation saved by Generate:', [f['text'][:17] for f in api('/api/state')['settings']['foundations'] if f['id'] == 'normal'])
        print('row button now:', (await pg.text_content('#bdGrid [data-write="1-male"]')).strip())
        print('markdown stripped:', not any('##' in d['prompt'] or '**' in d['prompt'] for d in b['drafts']))
        await until(pg, "() => document.querySelectorAll('#bdGrid .lab img').length >= 8 && !document.querySelector('#bdGrid .lab .wait')", 60)
        runs = [r for r in api('/api/runs')['runs'] if r['kind'] == 'build']
        print('images:', len(runs), '(4 faces x 2 models expected) | full prompt starts with foundation:', all(r['fullPrompt'].startswith('SIMPLE FACE RULES') for r in runs), '| adult -> moderation low:', all(r.get('moderation') == 'low' for r in runs))
        # Full prompt box: exact text (foundation + combination prompt), settings and pictures sent, copy, close
        sfr = [r for r in runs if r['variant'] == '1-female' and r['model'] == 'openai-direct/gpt-image-2'][0]
        await pg.click(f'#bdGrid .lab[data-id="{sfr["id"]}"] [data-full]'); await pg.wait_for_timeout(300)
        print('full prompt box open:', await pg.is_visible('#fullP'), '| title:', await pg.text_content('#fpTitle'))
        secs = await pg.eval_on_selector_all('#fpText .sec', 'els => els.map(e => e.textContent)'); pre = await pg.eval_on_selector_all('#fpText pre', 'els => els.map(e => e.textContent)')
        print('sections:', secs, '| foundation part right:', pre[0] == 'SIMPLE FACE RULES: realistic line art, single line thickness.', '| parts rejoin to the exact text sent:', pre[0] + '\n\n' + pre[1] == sfr['fullPrompt'])
        await pg.wait_for_timeout(500); print('face thumbnail loaded:', await pg.evaluate("(() => { const i = document.querySelector('#fpMeta img'); return !!i && i.naturalWidth > 0; })()"))
        meta = await pg.inner_text('#fpMeta'); print('meta:', ' | '.join(l for l in meta.split('\n') if l.strip()))
        rj = api('/api/runs'); rr = [x for x in rj['runs'] if x['id'] == sfr['id']][0]; print('recorded on the run:', rr.get('sentTo'), rr.get('sentParams'), rr.get('sentImages'))
        await pg.click('#fpCopy'); await pg.wait_for_timeout(200); print('copy button says:', await pg.text_content('#fpCopy'), '| clipboard matches:', (await pg.evaluate('navigator.clipboard.readText()')) == sfr['fullPrompt'])
        await pg.keyboard.press('Escape'); await pg.wait_for_timeout(150); print('Escape closes it:', not await pg.is_visible('#fullP'))
        fl = [r for r in runs if r['model'] == 'black-forest-labs/flux.2-pro'][0]; await pg.click(f'#bdGrid .lab[data-id="{fl["id"]}"] [data-full]'); await pg.wait_for_timeout(200)
        print('OpenRouter one:', ' | '.join(l for l in (await pg.inner_text('#fpMeta')).split('\n') if l.strip())[:220]); await pg.mouse.click(5, 5); await pg.wait_for_timeout(150); print('click outside closes it:', not await pg.is_visible('#fullP'))
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
        # regenerate one row only
        n1 = len(api('/api/builder/space-pirates')['builder']['drafts']); await pg.click('#bdGrid [data-write="1-female"]'); await pg.wait_for_timeout(600); await until(pg, "() => !document.querySelector('#bdGrid .draft .spin')")
        nd = api('/api/builder/space-pirates')['builder']['drafts'][n1:]; print('regenerate single female wrote:', [d['variant'] for d in nd])
        # save as a new foundation from the builder
        await pg.fill('#bdFoundText', 'BIG HEAD RULES: oversized head.'); ANS[0] = 'Big head v2'; await pg.click('#bdFoundNew'); await pg.wait_for_timeout(1000)
        st = api('/api/state'); print('new foundation:', [f['name'] for f in st['settings']['foundations']], '| theme now uses:', [t['settings'].get('foundation') for t in st['themes'] if t['slug'] == 'space-pirates'], '| normal unchanged:', [f['text'][:17] for f in st['settings']['foundations'] if f['id'] == 'normal'])
        await pg.select_option('#bdFound', 'normal'); await pg.wait_for_timeout(600)
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
        # clear the page: first keeping the kept prompts, then everything
        kept_before = [v for v in t['prompts'] if t['prompts'][v].strip()]
        await pg.click('#bdClear'); await pg.wait_for_timeout(1500)
        b = api('/api/builder/space-pirates')['builder']; t = [x for x in api('/api/state')['themes'] if x['slug'] == 'space-pirates'][0]; left = [r for r in api('/api/runs')['runs'] if r['theme'] == 'space-pirates']
        print('clear (keep kept): kept prompts still', [v for v in t['prompts'] if t['prompts'][v].strip()], '(was', kept_before, ') | drafts left', len(b['drafts']), '| images left', len(left), '(the kept pictures) | kept runs intact:', all(r['id'] in [k['runId'] for k in b['kept'].values()] for r in left))
        await pg.check('#bdClearKept'); await pg.click('#bdClear'); await pg.wait_for_timeout(1500)
        b = api('/api/builder/space-pirates')['builder']; t = [x for x in api('/api/state')['themes'] if x['slug'] == 'space-pirates'][0]
        print('clear everything: prompts', [v for v in t['prompts'] if t['prompts'][v].strip()], '| drafts', len(b['drafts']), '| images', len([r for r in api('/api/runs')['runs'] if r['theme'] == 'space-pirates']), '| description kept:', bool(b['description']), '| page shows:', (await pg.text_content('#bdProgress')).strip())
        # consolidated Prompt test still works
        await pg.click('#nav [data-t=matrix]'); await pg.wait_for_timeout(300)
        print('prompt test title:', (await pg.text_content('#tab-matrix h2'))[:12], '| face picker has faces:', len(await pg.query_selector_all('#mxFaces .face')))
        await pg.click('#mxFaces .face img'); await pg.fill('#mxPrompts .mxText', 'pirate test'); await pg.evaluate("() => document.querySelectorAll('#mxModels input').forEach(i => i.checked = i.value === 'openai-direct/gpt-image-2')")
        await pg.click('#mxRun'); await pg.wait_for_timeout(2500); print('prompt test results:', len(await pg.query_selector_all('#mxGrid .lab')))
        await pg.click('#mxGrid .lab [data-full]'); await pg.wait_for_timeout(200); print('prompt test full prompt:', await pg.eval_on_selector_all('#fpText .sec', 'els => els.map(e => e.textContent)'), (await pg.inner_text('#fpText pre'))[:40]); await pg.screenshot(path=SHOT.replace('.png', '-full.png')); await pg.click('#fpClose')
        print('ERRORS:', errs or 'none'); await br.close()
asyncio.run(main())
