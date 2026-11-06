"""★ Keep all prompts (no images needed) and ★ Keep on a single draft, then the booth export. Run: LTEST=test/keepall.py bash test/run.sh"""
import asyncio, io, json, os, sys, zipfile, urllib.request
from playwright.async_api import async_playwright
B = 'http://localhost:3457'; fails = []
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
        br = await p.chromium.launch(); pg = await (await br.new_context(viewport={'width': 1400, 'height': 1100})).new_page(); errs, dialogs = [], []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        def on_dialog(d): dialogs.append(d.message); asyncio.ensure_future(d.accept('Space Pirates') if d.type == 'prompt' else d.accept())
        pg.on('dialog', on_dialog)
        await pg.goto(B + '/'); await pg.fill('#pw', 'pw'); await pg.click('#loginBtn'); await pg.wait_for_timeout(1500)
        await pg.click('#newTheme'); await pg.wait_for_timeout(1200); slug = await pg.input_value('#bdTheme')
        await pg.fill('#bdFoundText', 'FOUNDATION RULES.'); await pg.click('#bdFoundSave'); await pg.wait_for_timeout(400)
        await pg.fill('#bdDesc', 'Space pirates with ray guns.'); await pg.press('#bdDesc', 'Tab'); await pg.wait_for_timeout(3600)
        await pg.click('#bdKeepAll'); await pg.wait_for_timeout(400); msg = await pg.text_content('#toast'); check('Generate all prompts first' in msg, f'Keep all with no prompts yet says to generate first ({msg!r})')
        # write every prompt, test none (no faces)
        await pg.click('#bdWriteAll'); await pg.wait_for_timeout(500)
        await until(pg, "() => document.querySelectorAll('#bdGrid .draft .dp').length >= 9 && !document.querySelector('#bdGrid .draft .spin')")
        check(len([r for r in api('/api/runs')['runs'] if r.get('theme') == slug]) == 0, 'no images were made')
        # keep one by hand first (so Keep all must leave it alone), using the per-draft ★ Keep
        b = api(f'/api/builder/{slug}')['builder']; sm = [d for d in b['drafts'] if d['variant'] == '1-male'][0]
        await pg.click(f'#bdGrid [data-dkeep="{sm["id"]}"]'); await pg.wait_for_timeout(800)
        t = [x for x in api('/api/state')['themes'] if x['slug'] == slug][0]; check(t['prompts']['1-male'] == sm['prompt'], '★ Keep on a draft keeps it without an image')
        check(await pg.locator(f'#bdGrid [data-dkeep="{sm["id"]}"]').count() == 0, 'the kept draft no longer shows ★ Keep')
        # regenerate Single male: the newer draft must NOT replace the kept one on Keep all
        await pg.click('#bdGrid [data-write="1-male"]'); await pg.wait_for_timeout(600); await until(pg, "() => !document.querySelector('#bdGrid .draft .spin')")
        dialogs.clear(); await pg.click('#bdKeepAll'); await pg.wait_for_timeout(1200)
        check(dialogs and 'these 8 combinations' in dialogs[0] and 'Single male' not in dialogs[0], f'confirm lists the 8 not kept yet')
        t = [x for x in api('/api/state')['themes'] if x['slug'] == slug][0]; kept = [v for v in t['prompts'] if t['prompts'][v].strip()]
        check(len(kept) == 9, f'all 9 combinations kept ({len(kept)})'); check(t['prompts']['1-male'] == sm['prompt'], 'the one kept by hand stayed')
        b = api(f'/api/builder/{slug}')['builder']; check(all(k.get('runId') is None and k.get('draftId') for k in b['kept'].values()), 'kept without images (no image run recorded)')
        check('9 of 9' in await pg.text_content('#bdProgress'), 'page shows 9 of 9 kept')
        await pg.click('#bdKeepAll'); await pg.wait_for_timeout(300); check('already kept' in await pg.text_content('#toast'), 'Keep all again: everything is already kept')
        z = zipfile.ZipFile(io.BytesIO(api(f'/api/themes/export?slug={slug}&bake=1', raw=True))); names = sorted(n.split('/')[-1] for n in z.namelist())
        check(len([n for n in names if n.endswith('.md')]) == 9 and 'pet-alone.md' in names, f'export has all 9 prompt files {names}')
        sf = [n for n in z.namelist() if n.endswith('single-female.md')][0]; check(z.read(sf).decode().startswith('FOUNDATION RULES.'), 'exported prompts start with the foundation')
        tt = [n for n in z.namelist() if n.endswith('theme.txt')]; check(not tt or '.model' not in z.read(tt[0]).decode(), 'no image model set for untested prompts (booth uses its default)')
        await pg.screenshot(path=os.environ.get('SHOT', '/tmp/keepall.png'), full_page=False)
        check(not errs, f'no page errors {errs}'); await br.close()
    print('\nFAILED:' if fails else '\nALL PASSED', fails or ''); sys.exit(1 if fails else 0)
asyncio.run(main())
