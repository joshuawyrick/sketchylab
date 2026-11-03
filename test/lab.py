import asyncio, json, urllib.request
from playwright.async_api import async_playwright
B='http://localhost:3457'; ZIP='/tmp/claude-0/-home-claude/ee2fe1e7-7782-5765-90bd-a94eed62b42f/scratchpad/themes.zip'; FACE='/home/claude/dexdraw/test/face.png'
def api(path, body=None, method=None):
    r=urllib.request.Request(B+path, data=json.dumps(body).encode() if body is not None else None, method=method or ('POST' if body is not None else 'GET'), headers={'x-admin-token':'pw','content-type':'application/json'})
    return json.load(urllib.request.urlopen(r))
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(); pg = await (await br.new_context(viewport={'width':1400,'height':1100})).new_page(); errs=[]; pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('dialog', lambda d: asyncio.ensure_future(d.accept()))
        await pg.goto(B+'/'); await pg.fill('#pw','pw'); await pg.click('#loginBtn'); await pg.wait_for_timeout(1500)
        await pg.click('#nav [data-t=settings]'); await pg.wait_for_timeout(1200); print('key:', (await pg.text_content('#keyState')).strip()[:40], '| models listed:', await pg.text_content('#modelCount'))
        await pg.uncheck('#modelEditsOnly'); await pg.wait_for_timeout(200); print('with text-only:', await pg.text_content('#modelCount')); await pg.check('#modelEditsOnly')
        for v in ['google/gemini-3.1-flash-image-preview', 'black-forest-labs/flux.2-pro']: await pg.check(f'#sModels input[value="{v}"]')
        await pg.select_option('#sQuality', 'high'); await pg.click('#sSave'); await pg.wait_for_timeout(1000); st = api('/api/state'); print('saved models:', st['settings']['models'], '| quality:', st['settings']['quality'])
        # themes: import zip
        await pg.click('#nav [data-t=themes]'); await pg.set_input_files('#impIn', ZIP); await pg.wait_for_timeout(2500); print('themes:', [ (t['name'], sum(1 for v in t['prompts'].values() if v), t['hasThumb'], t['settings']) for t in api('/api/state')['themes'] ])
        # faces + lab run
        await pg.click('#nav [data-t=lab]'); await pg.wait_for_timeout(400); await pg.set_input_files('#faceIn', [FACE, FACE]); await pg.wait_for_timeout(1500); print('faces (same file twice -> 1):', len(api('/api/faces')['faces']))
        await pg.click('#ltSlots .slot[data-v="1-female"]'); await pg.click('#ltSlots .slot[data-v="1-male"]'); await pg.wait_for_timeout(300); print('slots:', len(await pg.query_selector_all('#ltSlots .slot.has')), '| models ticked:', len(await pg.query_selector_all('#ltModels input:checked')))
        await pg.click('#ltRun'); await pg.wait_for_timeout(600); print('msg:', await pg.text_content('#ltMsg'), '| cards:', len(await pg.query_selector_all('#ltGrid .lab')))
        for i in range(40):
            await pg.wait_for_timeout(500)
            if not await pg.query_selector('#ltGrid .wait'): break
        done = [r for r in api('/api/runs')['runs'] if r['status']=='done']; failed = [r for r in api('/api/runs')['runs'] if r['status']=='failed']
        print('done:', len(done), '| failed:', [(r['model'], r['error']) for r in failed], '| dropped:', [r.get('dropped') for r in done if r.get('dropped')], '| costs:', [r['cost'] for r in done][:2])
        print('gallery:', (await pg.text_content('#galCount')).strip())
        await pg.reload(); await pg.wait_for_timeout(1500); print('after reload cards:', len(await pg.query_selector_all('#ltGrid .lab')), '| slots remembered:', len(await pg.query_selector_all('#ltSlots .slot.has')))
        await (await pg.query_selector('#ltGrid [data-star]')).click(); await pg.wait_for_timeout(800); await pg.click('#galClear'); await pg.wait_for_timeout(1200); print('after clear (starred kept):', len(await pg.query_selector_all('#ltGrid .lab')))
        await (await pg.query_selector('#ltGrid [data-apply]')).click(); await pg.wait_for_timeout(1200); t = api('/api/state')['themes'][0]; print('apply -> settings:', t['settings'])
        await (await pg.query_selector('#ltGrid [data-thumb]')).click(); await pg.wait_for_timeout(1000)
        # studio
        await pg.click('#nav [data-t=studio]'); await pg.fill('#stPrompt', 'test REFUSEME prompt'); await pg.check('#stModels input[value="openai/gpt-image-1"]'); await pg.click('#stRun'); await pg.wait_for_timeout(2500); print('studio refusal shown:', 'moderation' in (await pg.text_content('#stGrid')))
        await pg.fill('#stPrompt', 'a clean prompt'); await pg.click('#stRun')
        for i in range(30):
            await pg.wait_for_timeout(500)
            if not await pg.query_selector('#stGrid .wait'): break
        print('studio cards:', len(await pg.query_selector_all('#stGrid .lab')), '| with image:', len(await pg.query_selector_all('#stGrid .lab img')))
        csv = urllib.request.urlopen(urllib.request.Request(B+'/api/costs.csv', headers={'x-admin-token':'pw'})).read().decode(); print('cost csv total line:', [l for l in csv.splitlines() if l.startswith('TOTAL')])
        exp = urllib.request.urlopen(urllib.request.Request(B+'/api/themes/export', headers={'x-admin-token':'pw'})).read(); print('export zip bytes:', len(exp))
        print('ERRORS:', errs or 'none'); await br.close()
asyncio.run(main())
# favorites
async def favs():
    async with async_playwright() as p:
        br = await p.chromium.launch(); pg = await br.new_page(); errs=[]; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(B+'/'); await pg.fill('#pw','pw'); await pg.click('#loginBtn'); await pg.wait_for_timeout(1500); await pg.click('#nav [data-t=settings]'); await pg.wait_for_timeout(1200)
        await pg.click('#sModels [data-fav="black-forest-labs/flux.2-pro"]'); await pg.wait_for_timeout(600); print('favorites:', api('/api/state')['settings']['favorites'], '| count text:', await pg.text_content('#modelCount'))
        await pg.click('#nav [data-t=lab]'); await pg.click('#ltFav'); await pg.wait_for_timeout(200); print('fav-only ticked:', [await i.get_attribute('value') for i in await pg.query_selector_all('#ltModels input:checked')], '| first listed:', await pg.get_attribute('#ltModels input', 'value'))
        print('card has model-star:', await pg.is_visible('#ltGrid [data-favm]'))
        print('ERRORS:', errs or 'none'); await br.close()
asyncio.run(favs())
