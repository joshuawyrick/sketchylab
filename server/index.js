/* Sketchy Lab — prompt test lab for Sketchy Robotics themes
   One page (/) behind the admin password. Themes come in as zips (same format as the booth), faces are a library,
   runs go to OpenRouter's image API so many models can be compared side by side. Everything lives in DATA_DIR.
*/
const express = require('express');
const multer = require('multer');
const sharp = require('sharp');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.join(__dirname, '..');
const DATA = process.env.DATA_DIR || path.join(ROOT, 'data');
const THEMES = path.join(DATA, 'themes'), FACES = path.join(DATA, 'faces'), RUNS = path.join(DATA, 'runs');
const SETTINGS_FILE = path.join(DATA, 'settings.json');
for (const d of [DATA, THEMES, FACES, RUNS]) fs.mkdirSync(d, { recursive: true });

// ---------- durable storage mirror (Replit Object Storage) — same scheme as the booth ----------
let bucket = null;
const IS_DEPLOYMENT = process.env.REPLIT_DEPLOYMENT === '1' || process.env.STORAGE_WRITE === '1';
const BUCKET_ID = process.env.OBJECT_STORAGE_BUCKET || process.env.DEFAULT_OBJECT_STORAGE_BUCKET_ID || process.env.DEFAULT_OBJECT_STORAGE_BUCKET || '';
try { if (BUCKET_ID || process.env.REPL_ID) { const { Client } = require(process.env.OBJECT_STORAGE_MODULE || '@replit/object-storage'); bucket = new Client(BUCKET_ID ? { bucketId: BUCKET_ID } : undefined); } } catch (e) { console.log('object storage not available:', e.message); bucket = null; }
const rel = f => path.relative(DATA, f).split(path.sep).join('/');
function persist(file) { if (!bucket || !IS_DEPLOYMENT) return; const key = rel(file); fs.promises.readFile(file).then(buf => bucket.uploadFromBytes(key, buf)).then(r => { if (r && !r.ok) console.error('storage upload failed', key, r.error && r.error.message); }).catch(e => console.error('storage upload', key, e.message)); }
function unpersistFile(f) { if (!bucket || !IS_DEPLOYMENT) return; bucket.delete(rel(f)).catch(() => {}); }
function unpersist(prefix) { if (!bucket || !IS_DEPLOYMENT) return; bucket.list().then(r => { if (!r.ok) return; for (const o of r.value) if (o.name.startsWith(rel(prefix) + '/')) bucket.delete(o.name).catch(() => {}); }).catch(() => {}); }
const toBuf = d => Array.isArray(d.value) ? Buffer.concat(d.value.map(x => Buffer.isBuffer(x) ? x : Buffer.from(x))) : Buffer.from(d.value);
async function download(key, dest) { let d; try { d = await bucket.downloadAsBytes(key); } catch (e) { return false; } if (!d.ok) return false; fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.writeFileSync(dest, toBuf(d)); return true; }
async function ensureLocal(file) { if (fs.existsSync(file)) return true; if (!bucket) return false; return download(rel(file), file); }
async function restoreFromBucket() {
  if (!bucket) { console.log('storage: local disk only (no Replit bucket)'); return; }
  const r = await bucket.list().catch(e => ({ ok: false, error: e }));
  if (!r.ok) { console.log('storage: bucket unreachable, local disk only:', r.error && r.error.message); bucket = null; return; }
  if (IS_DEPLOYMENT) { for (const d of [THEMES, FACES, RUNS]) { fs.rmSync(d, { recursive: true, force: true }); fs.mkdirSync(d, { recursive: true }); } fs.rmSync(SETTINGS_FILE, { force: true }); }
  let n = 0;
  for (const o of r.value) {
    if (!o.name || o.name.endsWith('/') || !/^(themes|faces|runs)\/|^settings\.json$/.test(o.name)) continue;
    if (IS_DEPLOYMENT && /\/(out\.png|thumb\.png)$/.test(o.name)) continue; // images: fetched when first shown
    if (await download(o.name, path.join(DATA, o.name))) n++;
  }
  console.log(`storage: Replit bucket connected, restored ${n} file(s)` + (IS_DEPLOYMENT ? '' : ' — dev workspace: read-only'));
}

const PORT = process.env.PORT || 3000;
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'sketchy';
const OR_KEY = process.env.OPENROUTER_API_KEY || '';
const OR_BASE = process.env.OPENROUTER_BASE || 'https://openrouter.ai/api/v1';
const OAI_KEY = process.env.OPENAI_API_KEY || '';          // optional: your own OpenAI key — its image models show up as "openai-direct/…"
const OAI_BASE = process.env.OPENAI_BASE || 'https://api.openai.com/v1';
const DIRECT = 'openai-direct/';                            // model-id prefix for models that go straight to OpenAI instead of OpenRouter
const PARALLEL = Math.max(1, Math.min(8, +process.env.LAB_PARALLEL || 4));

// ---------- themes (same files as the booth: theme.json, prompts/<variant>.txt, thumb.png) ----------
const VARIANTS = ['1-male', '1-female', '2-male-male', '2-female-female', '2-male-female', '2-female-male', 'pet-male', 'pet-female'];
const VARIANT_LABELS = { '1-male': 'Single male', '1-female': 'Single female', '2-male-male': 'Two males', '2-female-female': 'Two females', '2-male-female': 'Male (left) + female (right)', '2-female-male': 'Female (left) + male (right)', 'pet-male': 'Male + pet', 'pet-female': 'Female + pet' };
const VARIANT_FILES = { '1-male': ['single-male', '1-male', 'male', 'man'], '1-female': ['single-female', '1-female', 'female', 'woman'], '2-male-male': ['two-males', '2-male-male', 'male-male', 'two-men'], '2-female-female': ['two-females', '2-female-female', 'female-female', 'two-women'], '2-male-female': ['male-left-female-right', '2-male-female', 'male-female'], '2-female-male': ['female-left-male-right', '2-female-male', 'female-male'], 'pet-male': ['male-pet', 'pet-male', 'man-pet'], 'pet-female': ['female-pet', 'pet-female', 'woman-pet'] };
const slugify = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'theme';
function readTheme(slug) {
  const dir = path.join(THEMES, slug); if (!fs.existsSync(path.join(dir, 'theme.json'))) return null;
  const t = JSON.parse(fs.readFileSync(path.join(dir, 'theme.json'), 'utf8')); t.slug = slug; t.prompts = {};
  for (const v of VARIANTS) { const f = path.join(dir, 'prompts', v + '.txt'); t.prompts[v] = fs.existsSync(f) ? fs.readFileSync(f, 'utf8') : ''; }
  t.hasThumb = fs.existsSync(path.join(dir, 'thumb.png')); t.settings = t.settings || {}; return t;
}
const listThemes = () => fs.readdirSync(THEMES).map(readTheme).filter(Boolean).sort((a, b) => a.name.localeCompare(b.name));
function writeTheme(slug, t) {
  const dir = path.join(THEMES, slug); fs.mkdirSync(path.join(dir, 'prompts'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'theme.json'), JSON.stringify({ name: t.name, settings: t.settings || {}, createdAt: t.createdAt || Date.now() }, null, 2)); persist(path.join(dir, 'theme.json'));
  if (t.prompts) for (const v of VARIANTS) if (v in t.prompts) { const f = path.join(dir, 'prompts', v + '.txt'); fs.writeFileSync(f, String(t.prompts[v] || '')); persist(f); }
}
const normName = n => String(n).toLowerCase().replace(/\.(md|markdown|txt)$/, '').replace(/[\s_\-]+/g, '');
const variantFor = name => { const k = normName(name); for (const v of VARIANTS) if (VARIANT_FILES[v].some(a => a.replace(/-/g, '') === k)) return v; return null; };
function parseZipThemes(buf, targetName) {
  const AdmZip = require('adm-zip'); const zip = new AdmZip(buf); const themes = new Map();
  for (const e of zip.getEntries()) { if (e.isDirectory) continue; const parts = e.entryName.split('/').filter(p => p && p !== '.'); if (parts.some(p => p.startsWith('__MACOSX') || p.startsWith('.'))) continue;
    const file = parts[parts.length - 1]; const theme = targetName || (parts.length >= 2 ? parts[parts.length - 2] : null); if (!theme) continue;
    const t = themes.get(theme) || { name: theme, prompts: {}, thumb: null, settings: {}, unknown: [] }; themes.set(theme, t);
    const low = file.toLowerCase();
    if (/^thumbnail\.(png|jpe?g|webp)$/.test(low)) { t.thumb = e.getData(); continue; }
    if (low === 'theme.txt' || low === 'theme.md') { for (const line of e.getData().toString('utf8').split(/\r?\n/)) { const m = line.match(/^\s*([\w.\-]+)\s*:\s*(.+?)\s*$/); if (m) t.settings[m[1].toLowerCase()] = m[2]; } continue; }
    if (!/\.(md|markdown|txt)$/i.test(low)) { t.unknown.push(file); continue; }
    const v = variantFor(file); if (!v) { t.unknown.push(file); continue; } t.prompts[v] = e.getData().toString('utf8').replace(/^﻿/, '').trim(); }
  return [...themes.values()];
}

// ---------- settings ----------
const DEFAULT_SETTINGS = { models: ['openai/gpt-image-1'], favorites: [], hidden: [], foundations: [{ id: 'normal', name: 'Normal', text: '' }, { id: 'bighead', name: 'Big head', text: '' }], quality: '', resolution: '1K', aspect: '2:3', background: '', moderation: '', note: '', refinePrompt: '', judgeModel: 'gpt-5.4-mini', autoJudge: false };
const DEFAULT_REFINE = `Image 1 is a black-line drawing; image 2 is a photo of the real person it depicts. Change ONLY the line quality of image 1. Make every stroke one uniform thin round-capped black line of identical width; remove every fill, grey tone, gradient, shadow, hatching, stippling and texture; open any filled pupil into a small ring inside an open iris with white between; keep every enclosed area pure white; keep at least two line-widths of white between separate strokes; delete stray specks and fragments. Do not change the face, likeness, expression, pose, hair silhouette, costume, props, composition or framing in any way, and do not add anything. Pure white background, no text. Output exactly one image.`;
const refineText = s => (s.refinePrompt || '').trim() || DEFAULT_REFINE;
const getSettings = () => { try { return Object.assign({}, DEFAULT_SETTINGS, JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf8'))); } catch (_) { return Object.assign({}, DEFAULT_SETTINGS); } };
const saveSettings = s => { fs.writeFileSync(SETTINGS_FILE, JSON.stringify(s, null, 2)); persist(SETTINGS_FILE); };

/** the foundation text that goes in front of a prompt: pick = 'none' | foundation id | '' (use the theme's choice) */
function foundationFor(theme, pick) { const s = getSettings(); const want = pick === 'none' ? null : pick || (theme && (theme.settings.foundation || (theme.settings.proportions === 'bighead' ? 'bighead' : 'normal'))); if (!want) return null; const f = (s.foundations || []).find(x => x.id === want); return f && f.text.trim() ? f : null; }
const withFoundation = (f, prompt) => f ? f.text.trim() + '\n\n' + prompt : prompt;
// ---------- OpenRouter ----------
let modelCache = { at: 0, list: [] };
async function orModels(force) { // image-capable models; cached for 10 minutes. supported_parameters is an object keyed by parameter name
  if (!OR_KEY) return [];
  if (!force && Date.now() - modelCache.at < 600000 && modelCache.list.length) return modelCache.list;
  const r = await fetch(OR_BASE + '/images/models', { headers: { Authorization: 'Bearer ' + OR_KEY } }); const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((d.error && d.error.message) || `OpenRouter ${r.status}`);
  const raw = Array.isArray(d.data) ? d.data : Array.isArray(d.models) ? d.models : Array.isArray(d) ? d : [];
  const list = raw.map(m => { const id = m.id || m.slug || m.canonical_slug; const spRaw = m.supported_parameters || m.supportedParameters || {}; const sp = Array.isArray(spRaw) ? spRaw : Object.keys(spRaw); const refs = !Array.isArray(spRaw) && spRaw.input_references && spRaw.input_references.max != null ? +spRaw.input_references.max : null;
    const arch = m.architecture || {}; const inp = m.input_modalities || arch.input_modalities || []; const out = m.output_modalities || arch.output_modalities || ['image'];
    return { id, name: m.name || id, edits: (sp.includes('input_references') && refs !== 0) || inp.includes('image'), params: sp, price: priceOf(m.pricing), pricing: m.pricing || null, provider: String(id).split('/')[0], out }; }).filter(m => m.id && m.out.includes('image'));
  modelCache = { at: Date.now(), list }; fillPrices(list).catch(() => {}); return list;
}
function priceOf(pr) { if (!pr || typeof pr !== 'object') return null; for (const k of ['image', 'per_image', 'image_output', 'output_image']) if (pr[k] != null && isFinite(+pr[k])) return +pr[k]; return null; }
const priceCache = new Map(); // model id -> per-image USD or null (from the per-model endpoints listing, fetched in the background)
async function fillPrices(list) { const todo = list.filter(m => m.price == null && !priceCache.has(m.id)); let i = 0;
  const worker = async () => { while (i < todo.length) { const m = todo[i++]; try { const r = await fetch(`${OR_BASE}/images/models/${m.id}/endpoints`, { headers: { Authorization: 'Bearer ' + OR_KEY } }); const d = await r.json().catch(() => ({})); const eps = (d.data && (d.data.endpoints || d.data)) || d.endpoints || []; const arr = Array.isArray(eps) ? eps : [eps]; let p = null; for (const e of arr) { p = priceOf(e && e.pricing); if (p != null) break; } priceCache.set(m.id, p); } catch (_) { priceCache.set(m.id, null); } } };
  await Promise.all(Array.from({ length: 6 }, worker)); for (const m of list) if (m.price == null && priceCache.has(m.id)) m.price = priceCache.get(m.id); }
// ---------- OpenAI direct (your own key) ----------
const OAI_FALLBACK = ['gpt-image-2.5-sunburst', 'gpt-image-2.5-flare', 'gpt-image-2', 'chatgpt-image-latest']; // gpt-image-1 retired Oct 2026, 1.5 retires Dec 2026
let oaiCache = { at: 0, list: [] };
const oaiModel = id => ({ id: DIRECT + id, name: 'OpenAI direct: ' + id, edits: true, params: ['quality', 'size', 'input_fidelity'], price: null, pricing: null, provider: 'openai-direct', out: ['image'], direct: true });
async function oaiModels(force) { // image models on the OpenAI account; falls back to the known list if the listing fails
  if (!OAI_KEY) return [];
  if (!force && Date.now() - oaiCache.at < 600000 && oaiCache.list.length) return oaiCache.list;
  let ids = [];
  try { const r = await fetch(OAI_BASE + '/models', { headers: { Authorization: 'Bearer ' + OAI_KEY } }); const d = await r.json().catch(() => ({})); if (r.ok && Array.isArray(d.data)) ids = d.data.map(m => m.id).filter(id => /^(gpt-image|chatgpt-image)/.test(id)); } catch (_) {}
  if (!ids.length) ids = OAI_FALLBACK;
  const list = ids.sort().map(oaiModel); oaiCache = { at: Date.now(), list }; return list;
}
const allModels = async force => (await Promise.all([orModels(force).catch(e => { if (!OAI_KEY) throw e; return []; }), oaiModels(force)])).flat();
const oaiSize = (aspect, model) => { const g2 = /gpt-image-2/.test(model); return ({ '2:3': '1024x1536', '3:4': g2 ? '1152x1536' : '1024x1536', '9:16': g2 ? '864x1536' : '1024x1536', '1:1': '1024x1024', '4:3': g2 ? '1536x1152' : '1536x1024', '16:9': g2 ? '1536x864' : '1536x1024' })[aspect] || null; };
const oaiCost = (model, u) => { if (!u) return null; const det = u.input_tokens_details || {}; const img = det.image_tokens || 0, txt = det.text_tokens || (u.input_tokens || 0) - img; const r = /^gpt-image-1(\.5)?$/.test(model) ? [40, 10, 5] : /^gpt-image-2/.test(model) ? [30, 8, 5] : null; if (!r) return null; return Math.round(((u.output_tokens || 0) * r[0] + img * r[1] + txt * r[2]) / 1e6 * 1e4) / 1e4; }; // published per-million token rates: gpt-image-1/1.5 and gpt-image-2/2.5
async function oaiImage(run) { // one OpenAI model on one face, straight to api.openai.com — returns { png, cost, ms, sent }
  if (!OAI_KEY) throw new Error('OPENAI_API_KEY is not set in Secrets');
  const model = run.model.slice(DIRECT.length); const imgs = await inputImages(run); const face = imgs.length ? imgs : null; const s = getSettings(); const o = run.opts || {};
  const fields = { model, prompt: run.fullPrompt || run.prompt, n: '1' };
  const q = o.quality || s.quality; if (q) fields.quality = (q === 'xhigh' || q === 'max') && !/gpt-image-2\.5/.test(model) ? 'high' : q; // xhigh/max exist only on 2.5
  const size = oaiSize(o.aspect || s.aspect, model); if (size) fields.size = size;
  if (s.background && !/gpt-image-2/.test(model)) fields.background = s.background;
  if (face && /^gpt-image-1(\.5)?$/.test(model)) fields.input_fidelity = 'high'; // gpt-image-2+ always use high input fidelity and reject the parameter
  const mod = run.moderation || s.moderation; if (mod === 'low' || mod === 'auto') fields.moderation = mod;
  if (!/dall-e/.test(model)) fields.output_format = 'png';
  const t0 = Date.now(); const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), 240000);
  const tryOnce = async () => { let r;
    if (face) { const fd = new FormData(); for (const [k, v] of Object.entries(fields)) fd.append(k, v); for (const im of imgs) fd.append('image[]', new Blob([im.buf], { type: im.mime }), im.name); r = await fetch(OAI_BASE + '/images/edits', { method: 'POST', headers: { Authorization: 'Bearer ' + OAI_KEY }, body: fd, signal: ctrl.signal }); }
    else r = await fetch(OAI_BASE + '/images/generations', { method: 'POST', headers: { Authorization: 'Bearer ' + OAI_KEY, 'content-type': 'application/json' }, body: JSON.stringify(Object.assign({}, fields, { n: 1 })), signal: ctrl.signal });
    const d = await r.json().catch(() => ({})); return { r, d }; };
  try {
    let { r, d } = await tryOnce();
    for (let i = 0; i < 3 && !r.ok && r.status === 400; i++) { const msg = ((d.error && d.error.message) || '').toLowerCase(); const k = ['quality', 'size', 'input_fidelity', 'background', 'output_format'].find(k => k in fields && msg.includes(k.replace('_', ' ')) || msg.includes(k)); if (!k) break; delete fields[k]; run.dropped = (run.dropped || []).concat(k); ({ r, d } = await tryOnce()); }
    if ((r.status === 429 || r.status >= 500) && !run.retried) { run.retried = true; await new Promise(x => setTimeout(x, 8000)); ({ r, d } = await tryOnce()); }
    if (!r.ok) throw new Error((d.error && d.error.message) || `OpenAI ${r.status}`);
    const item = d.data && d.data[0]; if (!item || !item.b64_json) throw new Error('no image in the response');
    let png = Buffer.from(item.b64_json, 'base64'); if (fields.output_format !== 'png') png = await sharp(png).png().toBuffer();
    return { png, cost: oaiCost(model, d.usage), ms: Date.now() - t0, sent: Object.keys(fields).filter(k => k !== 'prompt' && k !== 'n') };
  } finally { clearTimeout(timer); }
}
/** the reference images a run sends: a refine run sends the drawing it refines first, then the real face (if any); a normal run sends the face */
async function inputImages(run) { const out = []; if (run.refineOf) { const f = path.join(RUNS, run.refineOf, 'out.png'); if (await ensureLocal(f)) out.push({ buf: fs.readFileSync(f), mime: 'image/png', name: 'drawing.png' }); } const face = run.face ? await faceBuffer(run.face) : null; if (face) out.push({ buf: face, mime: 'image/jpeg', name: 'face.jpg' }); return out; }
const genImage = run => run.model.startsWith(DIRECT) ? oaiImage(run) : orImage(run);
async function orImage(run) { // one model on one face — returns { png, cost, ms }
  if (!OR_KEY) throw new Error('OPENROUTER_API_KEY is not set in Secrets');
  const imgs = await inputImages(run); const s = getSettings();
  const body = { model: run.model, prompt: run.fullPrompt || run.prompt, n: 1, output_format: 'png' };
  if (imgs.length) body.input_references = imgs.map(im => ({ type: 'image_url', image_url: { url: `data:${im.mime};base64,` + im.buf.toString('base64') } }));
  const o = run.opts || {}; if (o.quality || s.quality) body.quality = o.quality || s.quality; if (o.resolution || s.resolution) body.resolution = o.resolution || s.resolution; if (o.aspect || s.aspect) body.aspect_ratio = o.aspect || s.aspect; if (s.background) body.background = s.background;
  const t0 = Date.now(); const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), 240000);
  const tryOnce = async () => { const r = await fetch(OR_BASE + '/images', { method: 'POST', headers: { Authorization: 'Bearer ' + OR_KEY, 'content-type': 'application/json', 'HTTP-Referer': 'https://sketchyrobotics.com', 'X-Title': 'Sketchy Lab' }, body: JSON.stringify(body), signal: ctrl.signal }); const d = await r.json().catch(() => ({})); return { r, d }; };
  try {
    let { r, d } = await tryOnce();
    // a parameter this model rejects (quality/resolution/aspect) → drop it and go again, like the booth does
    for (let i = 0; i < 3 && !r.ok && r.status === 400; i++) { const msg = ((d.error && d.error.message) || '').toLowerCase(); const k = ['quality', 'resolution', 'aspect_ratio', 'background', 'output_format'].find(k => k in body && msg.includes(k.replace('_', ' ')) || msg.includes(k)); if (!k) break; delete body[k]; run.dropped = (run.dropped || []).concat(k); ({ r, d } = await tryOnce()); }
    if ((r.status === 429 || r.status >= 500) && !run.retried) { run.retried = true; await new Promise(x => setTimeout(x, 8000)); ({ r, d } = await tryOnce()); }
    if (!r.ok) throw new Error((d.error && d.error.message) || `OpenRouter ${r.status}`);
    const item = d.data && d.data[0]; if (!item || !item.b64_json) throw new Error('no image in the response');
    let png = Buffer.from(item.b64_json, 'base64'); if (item.media_type && !/png/.test(item.media_type)) png = await sharp(png).png().toBuffer();
    return { png, cost: d.usage && d.usage.cost != null ? +d.usage.cost : null, ms: Date.now() - t0, sent: Object.keys(body).filter(k => k !== 'input_references' && k !== 'prompt') };
  } finally { clearTimeout(timer); }
}

// ---------- likeness judge (OpenAI vision model looks at the photo and the drawing) ----------
async function judgeRun(r) {
  if (!OAI_KEY) throw new Error('OPENAI_API_KEY is needed for the likeness judge');
  const out = path.join(RUNS, r.id, 'out.png'); if (!(await ensureLocal(out))) throw new Error('no image to judge');
  const face = r.face ? await faceBuffer(r.face) : null; const s = getSettings(); const model = s.judgeModel || 'gpt-5.4-mini';
  const ask = face
    ? `Image 1 is a photo of a real person. Image 2 is a black-line drawing that is supposed to be a recognisable portrait of that same person, to be drawn by a pen plotter. Judge it strictly. Reply with JSON only, no prose: {"likeness": 1-10 (would a friend recognise this person? 10 = unmistakable), "eyes": 1-10, "nose": 1-10, "mouth": 1-10, "hair": 1-10, "plottable": 1-10 (10 = pure thin uniform outlines, white interiors, no fills/grey/texture/hatching), "problems": ["up to 4 short phrases naming the worst specific problems, e.g. filled pupils, jaw too narrow, hatching in hair"], "verdict": "one sentence"}`
    : `This is a black-line drawing meant to be drawn by a pen plotter with one thin pen. Judge it strictly. Reply with JSON only, no prose: {"plottable": 1-10 (10 = pure thin uniform outlines, white interiors, no fills/grey/texture/hatching), "problems": ["up to 4 short phrases naming the worst specific problems"], "verdict": "one sentence"}`;
  const content = [{ type: 'input_text', text: ask }]; if (face) content.push({ type: 'input_image', image_url: 'data:image/jpeg;base64,' + face.toString('base64'), detail: 'high' });
  content.push({ type: 'input_image', image_url: 'data:image/png;base64,' + fs.readFileSync(out).toString('base64'), detail: 'high' });
  const rsp = await fetch(OAI_BASE + '/responses', { method: 'POST', headers: { Authorization: 'Bearer ' + OAI_KEY, 'content-type': 'application/json' }, body: JSON.stringify({ model, input: [{ role: 'user', content }] }) });
  const d = await rsp.json().catch(() => ({})); if (!rsp.ok) throw new Error((d.error && d.error.message) || `OpenAI ${rsp.status}`);
  let text = d.output_text || ''; if (!text && Array.isArray(d.output)) for (const o of d.output) for (const c of (o.content || [])) if (c.type === 'output_text') text += c.text;
  const m = text.match(/\{[\s\S]*\}/); if (!m) throw new Error('judge gave no JSON: ' + text.slice(0, 120));
  const j = JSON.parse(m[0]); const n = v => v == null || isNaN(+v) ? null : Math.max(1, Math.min(10, Math.round(+v)));
  r.judge = { likeness: n(j.likeness), eyes: n(j.eyes), nose: n(j.nose), mouth: n(j.mouth), hair: n(j.hair), plottable: n(j.plottable), problems: Array.isArray(j.problems) ? j.problems.slice(0, 4).map(String) : [], verdict: String(j.verdict || '').slice(0, 200), model, at: Date.now() };
  saveRun(r); return r.judge;
}

// ---------- faces ----------
async function faceBuffer(id) { if (!/^[a-f0-9]{16}$/.test(id)) return null; const f = path.join(FACES, id + '.jpg'); return (await ensureLocal(f)) ? fs.readFileSync(f) : null; }
const listFaces = () => fs.readdirSync(FACES).filter(f => f.endsWith('.jpg')).map(f => ({ id: f.slice(0, -4), at: fs.statSync(path.join(FACES, f)).mtimeMs })).sort((a, b) => b.at - a.at);

// ---------- runs (one model × one combination × one face) ----------
const runs = new Map();
for (const id of fs.readdirSync(RUNS)) { try { const r = JSON.parse(fs.readFileSync(path.join(RUNS, id, 'run.json'), 'utf8')); if (r.status === 'processing') { r.status = 'failed'; r.error = 'server restarted mid-run'; } runs.set(r.id, r); } catch (_) {} }
function saveRun(r) { fs.mkdirSync(path.join(RUNS, r.id), { recursive: true }); const f = path.join(RUNS, r.id, 'run.json'); fs.writeFileSync(f, JSON.stringify(r, null, 2)); runs.set(r.id, r); persist(f); }
const pubRun = r => Object.assign({}, r, { out: r.status === 'done' ? `/api/runs/${r.id}/out` : null, face: r.face ? r.face : null });
const queue = []; let active = 0;
function enqueue(r) { r.status = 'processing'; r.note = 'queued'; saveRun(r); queue.push(r); pump(); }
function pump() {
  while (active < PARALLEL && queue.length) { const r = queue.shift(); active++; r.note = 'generating…'; r.startedAt = Date.now(); saveRun(r);
    genImage(r).then(async ({ png, cost, ms, sent }) => { fs.writeFileSync(path.join(RUNS, r.id, 'out.png'), png); persist(path.join(RUNS, r.id, 'out.png')); await sharp(png).resize(420, 420, { fit: 'inside' }).png().toFile(path.join(RUNS, r.id, 'thumb.png')); persist(path.join(RUNS, r.id, 'thumb.png'));
      Object.assign(r, { status: 'done', cost, seconds: Math.round(ms / 100) / 10, sent, note: null, error: null, doneAt: Date.now() }); saveRun(r);
      if (getSettings().autoJudge && OAI_KEY) { try { await judgeRun(r); } catch (e) { r.judgeError = String(e.message || e); } } })
      .catch(e => { Object.assign(r, { status: 'failed', error: String(e.message || e), note: null, doneAt: Date.now() }); console.error('run', r.id, r.model, r.error); })
      .finally(() => { saveRun(r); active--; setTimeout(pump, 50); }); }
}

// ---------- app ----------
const app = express();
app.use(express.json({ limit: '4mb' }));
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 60 * 1024 * 1024 } });
app.use('/', express.static(path.join(ROOT, 'public')));
const auth = (req, res, next) => { const t = req.get('x-admin-token') || req.query.token; if (t && t === ADMIN_PASSWORD) return next(); res.status(401).json({ error: 'bad password' }); };
app.post('/api/login', (req, res) => { if ((req.body.password || '') === ADMIN_PASSWORD) res.json({ ok: true, token: ADMIN_PASSWORD }); else res.status(401).json({ error: 'wrong password' }); });

app.get('/api/state', auth, (req, res) => res.json({ settings: Object.assign(getSettings(), { defaultRefine: DEFAULT_REFINE }), themes: listThemes(), variants: VARIANT_LABELS, variantOrder: VARIANTS, faces: listFaces(), hasKey: !!(OR_KEY || OAI_KEY), hasOpenAI: !!OAI_KEY, hasOpenRouter: !!OR_KEY, durable: !!bucket, readOnly: !!bucket && !IS_DEPLOYMENT, parallel: PARALLEL }));
app.post('/api/settings', auth, (req, res) => { const s = getSettings(); for (const k of ['models', 'favorites', 'hidden', 'foundations', 'quality', 'resolution', 'aspect', 'background', 'moderation', 'note', 'refinePrompt', 'judgeModel', 'autoJudge']) if (k in req.body) s[k] = req.body[k]; if (!Array.isArray(s.hidden)) s.hidden = []; if (Array.isArray(s.foundations)) s.foundations = s.foundations.map(f => ({ id: String(f.id || slugify(f.name || 'f')), name: String(f.name || '').slice(0, 40), text: String(f.text || '') })).filter(f => f.id && f.name); if (!Array.isArray(s.favorites)) s.favorites = []; if (!Array.isArray(s.models)) s.models = []; saveSettings(s); res.json(Object.assign({ ok: true }, s)); });
app.post('/api/favorites/toggle', auth, (req, res) => { const s = getSettings(); const id = String(req.body.model || ''); if (!id) return res.status(400).end(); s.favorites = (s.favorites || []).includes(id) ? s.favorites.filter(m => m !== id) : s.favorites.concat(id); saveSettings(s); res.json({ ok: true, favorites: s.favorites }); });
// hide a model everywhere in the lab (it's still on OpenRouter; un-hide it from Settings → "show hidden"). Hiding also drops it from favorites and the default ticks.
app.post('/api/hidden/toggle', auth, (req, res) => { const s = getSettings(); const id = String(req.body.model || ''); if (!id) return res.status(400).end(); const h = Array.isArray(s.hidden) ? s.hidden : [];
  if (h.includes(id)) s.hidden = h.filter(m => m !== id); else { s.hidden = h.concat(id); s.favorites = (s.favorites || []).filter(m => m !== id); s.models = (s.models || []).filter(m => m !== id); }
  saveSettings(s); res.json({ ok: true, hidden: s.hidden, favorites: s.favorites, models: s.models }); });
app.get('/api/models', auth, async (req, res) => { try { res.json({ models: await allModels(req.query.refresh === '1'), hasKey: !!(OR_KEY || OAI_KEY) }); } catch (e) { res.status(502).json({ error: e.message, hasKey: !!(OR_KEY || OAI_KEY) }); } });
app.get('/api/key', auth, async (req, res) => { // are the OpenRouter / OpenAI keys good (and OpenRouter's balance)
  const out = { configured: !!OR_KEY, openai: { configured: !!OAI_KEY } };
  if (OR_KEY) { try { const r = await fetch(OR_BASE + '/key', { headers: { Authorization: 'Bearer ' + OR_KEY } }); const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error((d.error && d.error.message) || `OpenRouter ${r.status}`); const k = d.data || d; Object.assign(out, { label: k.label, usage: k.usage, limit: k.limit, remaining: k.limit_remaining != null ? k.limit_remaining : null }); } catch (e) { out.error = e.message; } }
  if (OAI_KEY) { try { const r = await fetch(OAI_BASE + '/models', { headers: { Authorization: 'Bearer ' + OAI_KEY } }); const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error((d.error && d.error.message) || `OpenAI ${r.status}`); out.openai.models = (Array.isArray(d.data) ? d.data.map(m => m.id).filter(id => /^(gpt-image|chatgpt-image)/.test(id)) : []).length; } catch (e) { out.openai.error = e.message; } }
  res.json(out);
});

// themes
app.post('/api/themes/import', auth, upload.single('zip'), async (req, res) => {
  try {
    if (!req.file) return res.status(400).json({ error: 'no zip' }); const preview = req.query.preview === '1'; const replaceAll = req.query.mode === 'replace';
    const target = req.query.target ? readTheme(slugify(req.query.target)) : null; if (req.query.target && !target) return res.status(400).json({ error: 'target theme not found' });
    const found = parseZipThemes(req.file.buffer, target ? target.name : null); if (!found.length) return res.status(400).json({ error: target ? 'No prompt files found in the zip.' : 'No theme folders found — each theme must be a folder holding its prompt files.' });
    const report = [];
    for (const t of found) {
      const existing = listThemes().find(x => x.name.toLowerCase() === t.name.toLowerCase()); const slug = existing ? existing.slug : slugify(t.name);
      report.push({ name: t.name, slug, isNew: !existing, prompts: Object.keys(t.prompts).length, replaced: existing ? Object.keys(t.prompts).filter(v => existing.prompts[v].trim() && existing.prompts[v].trim() !== t.prompts[v]).map(v => VARIANT_LABELS[v]) : [], thumb: !!t.thumb, unknown: t.unknown });
      if (preview) continue;
      const base = existing || { name: t.name, prompts: {}, settings: {} }; const th = { name: base.name, createdAt: base.createdAt, settings: Object.assign({}, base.settings, t.settings), prompts: Object.assign({}, replaceAll ? {} : base.prompts, t.prompts) };
      if (replaceAll) for (const v of VARIANTS) if (!(v in th.prompts)) th.prompts[v] = '';
      writeTheme(slug, th);
      if (t.thumb) { try { await sharp(t.thumb).rotate().resize(700, 700, { fit: 'inside', withoutEnlargement: true }).png().toFile(path.join(THEMES, slug, 'thumb.png')); persist(path.join(THEMES, slug, 'thumb.png')); } catch (e) { report[report.length - 1].thumbError = e.message; } }
    }
    res.json({ ok: true, preview, themes: report });
  } catch (e) { res.status(500).json({ error: e.message }); }
});
app.get('/api/themes/export', auth, async (req, res) => {
  const AdmZip = require('adm-zip'); const zip = new AdmZip(); const which = req.query.slug ? listThemes().filter(t => t.slug === req.query.slug) : listThemes();
  for (const t of which) { const dir = t.name.replace(/[\\/:*?"<>|]/g, '-');
    const fd = req.query.bake === '1' ? foundationFor(t, '') : null; // bake=1: foundation text goes in front of every prompt file, so the booth draws exactly what the lab tested
    for (const v of VARIANTS) if (t.prompts[v] && t.prompts[v].trim()) zip.addFile(`${dir}/${VARIANT_FILES[v][0]}.md`, Buffer.from(withFoundation(fd, t.prompts[v].trim()), 'utf8'));
    const lines = Object.entries(t.settings || {}).map(([k, v]) => `${k}: ${v}`); if (lines.length) zip.addFile(`${dir}/theme.txt`, Buffer.from(lines.join('\n') + '\n', 'utf8'));
    const th = path.join(THEMES, t.slug, 'thumb.png'); if (await ensureLocal(th)) zip.addFile(`${dir}/thumbnail.png`, fs.readFileSync(th)); }
  res.setHeader('content-type', 'application/zip'); res.setHeader('content-disposition', `attachment; filename="${which.length === 1 ? which[0].name.replace(/[^\w.-]+/g, '-') : 'sketchy-themes'}.zip"`); res.send(zip.toBuffer());
});
app.post('/api/themes', auth, (req, res) => { const name = String(req.body.name || '').trim(); if (!name) return res.status(400).json({ error: 'name required' }); let slug = slugify(name); if (readTheme(slug)) slug += '-' + Date.now().toString(36); writeTheme(slug, { name, prompts: {}, settings: {} }); res.json(readTheme(slug)); });
app.put('/api/themes/:slug', auth, (req, res) => { const t = readTheme(slugify(req.params.slug)); if (!t) return res.status(404).end(); if (req.body.name) t.name = String(req.body.name).trim().slice(0, 60); if (req.body.prompts) for (const v of VARIANTS) if (v in req.body.prompts) t.prompts[v] = String(req.body.prompts[v] || ''); if (req.body.settings) t.settings = Object.assign({}, t.settings, req.body.settings); writeTheme(t.slug, t); res.json(readTheme(t.slug)); });
app.delete('/api/themes/:slug', auth, (req, res) => { const slug = slugify(req.params.slug); fs.rmSync(path.join(THEMES, slug), { recursive: true, force: true }); unpersist(path.join(THEMES, slug)); res.json({ ok: true }); });
app.get('/api/themes/:slug/thumb', auth, async (req, res) => { const f = path.join(THEMES, slugify(req.params.slug), 'thumb.png'); if (await ensureLocal(f)) res.sendFile(f); else res.status(404).end(); });
app.post('/api/themes/:slug/thumb', auth, upload.single('thumb'), async (req, res) => { const t = readTheme(slugify(req.params.slug)); if (!t || !req.file) return res.status(400).end(); await sharp(req.file.buffer).rotate().resize(700, 700, { fit: 'inside', withoutEnlargement: true }).png().toFile(path.join(THEMES, t.slug, 'thumb.png')); persist(path.join(THEMES, t.slug, 'thumb.png')); res.json({ ok: true }); });

// faces
app.get('/api/faces', auth, (req, res) => res.json({ faces: listFaces() }));
app.post('/api/faces', auth, upload.single('photo'), async (req, res) => { try { if (!req.file) throw new Error('no file received'); const buf = await sharp(req.file.buffer).rotate().resize(1536, 1536, { fit: 'inside', withoutEnlargement: true }).jpeg({ quality: 92 }).toBuffer(); const id = crypto.createHash('sha1').update(buf).digest('hex').slice(0, 16); const f = path.join(FACES, id + '.jpg'); if (!fs.existsSync(f)) { fs.writeFileSync(f, buf); persist(f); } res.json({ id, existed: fs.existsSync(f) }); } catch (e) { res.status(400).json({ error: 'could not read that photo: ' + e.message }); } });
app.get('/api/faces/:id', auth, async (req, res) => { const b = await faceBuffer(req.params.id); if (!b) return res.status(404).end(); res.setHeader('content-type', 'image/jpeg'); res.setHeader('cache-control', 'private, max-age=86400'); res.send(b); });
app.delete('/api/faces/:id', auth, (req, res) => { if (/^[a-f0-9]{16}$/.test(req.params.id)) { const f = path.join(FACES, req.params.id + '.jpg'); fs.rmSync(f, { force: true }); unpersistFile(f); } res.json({ ok: true }); });

// runs
app.get('/api/runs', auth, (req, res) => { let all = [...runs.values()].sort((a, b) => b.createdAt - a.createdAt); if (req.query.theme) all = all.filter(r => r.theme === req.query.theme); if (req.query.kind) all = all.filter(r => r.kind === req.query.kind); res.json({ runs: all.slice(0, +req.query.limit || 400).map(pubRun), active, queued: queue.length }); });
app.get('/api/runs/:id/out', auth, async (req, res) => { const f = path.join(RUNS, req.params.id, req.query.thumb ? 'thumb.png' : 'out.png'); if (!(await ensureLocal(f))) return res.status(404).end(); if (req.query.download) res.setHeader('content-disposition', `attachment; filename="${req.params.id}.png"`); res.sendFile(f); });
app.delete('/api/runs/:id', auth, (req, res) => { const r = runs.get(req.params.id); if (r) { runs.delete(r.id); fs.rmSync(path.join(RUNS, r.id), { recursive: true, force: true }); unpersist(path.join(RUNS, r.id)); } res.json({ ok: true }); });
app.post('/api/runs/clear', auth, (req, res) => { let n = 0; for (const r of [...runs.values()]) { if (req.body.theme && r.theme !== req.body.theme) continue; if (req.body.kind && r.kind !== req.body.kind) continue; if (req.body.keepStarred && r.star) continue; runs.delete(r.id); fs.rmSync(path.join(RUNS, r.id), { recursive: true, force: true }); unpersist(path.join(RUNS, r.id)); n++; } res.json({ ok: true, n }); });
app.post('/api/runs/:id/star', auth, (req, res) => { const r = runs.get(req.params.id); if (!r) return res.status(404).end(); r.star = !r.star; saveRun(r); res.json(pubRun(r)); });
app.post('/api/runs/:id/thumb', auth, async (req, res) => { // make this result a theme's thumbnail
  const r = runs.get(req.params.id); const t = r && readTheme(req.body.theme || r.theme); if (!r || !t) return res.status(404).end(); const f = path.join(RUNS, r.id, 'out.png'); if (!(await ensureLocal(f))) return res.status(404).json({ error: 'no image' });
  await sharp(f).resize(700, 700, { fit: 'inside', withoutEnlargement: true }).png().toFile(path.join(THEMES, t.slug, 'thumb.png')); persist(path.join(THEMES, t.slug, 'thumb.png')); res.json({ ok: true, theme: t.slug }); });
/** refine: a second pass that edits a finished drawing (plus the original face) with the refine prompt — same model unless { model } is given */
app.post('/api/runs/:id/refine', auth, async (req, res) => { const src = runs.get(req.params.id); if (!src || src.status !== 'done') return res.status(404).json({ error: 'no finished image to refine' });
  const f = path.join(RUNS, src.id, 'out.png'); if (!(await ensureLocal(f))) return res.status(404).json({ error: 'image missing' }); const s = getSettings();
  const r = Object.assign({}, src, { id: crypto.randomBytes(6).toString('hex'), model: typeof req.body.model === 'string' && req.body.model ? req.body.model : src.model, refineOf: src.id, refined: true, prompt: src.prompt, fullPrompt: refineText(s), judge: undefined, judgeError: undefined, star: false, cost: undefined, seconds: undefined, sent: undefined, dropped: undefined, retried: undefined, out: undefined, doneAt: undefined, createdAt: Date.now() });
  enqueue(r); res.json(pubRun(r)); });
app.post('/api/runs/:id/judge', auth, async (req, res) => { const r = runs.get(req.params.id); if (!r || r.status !== 'done') return res.status(404).json({ error: 'no finished image to judge' }); try { res.json({ ok: true, judge: await judgeRun(r) }); } catch (e) { r.judgeError = String(e.message || e); saveRun(r); res.status(502).json({ error: e.message }); } });
app.post('/api/runs/judge', auth, async (req, res) => { // judge every finished, unjudged run in a batch (or a list of ids)
  const ids = Array.isArray(req.body.ids) ? req.body.ids : [...runs.values()].filter(r => r.batch === req.body.batch).map(r => r.id); const todo = ids.map(id => runs.get(id)).filter(r => r && r.status === 'done' && (!r.judge || req.body.force));
  let n = 0; const errs = []; let i = 0; const worker = async () => { while (i < todo.length) { const r = todo[i++]; try { await judgeRun(r); n++; } catch (e) { r.judgeError = String(e.message || e); saveRun(r); errs.push(r.model + ': ' + e.message); } } };
  await Promise.all(Array.from({ length: 3 }, worker)); res.json({ ok: true, judged: n, errors: errs.slice(0, 5) }); });
app.post('/api/runs/:id/apply', auth, (req, res) => { // make this run's prompt the theme's saved prompt for its combination
  const r = runs.get(req.params.id); const t = r && readTheme(r.theme); if (!r || !t || !r.variant) return res.status(404).end(); t.prompts[r.variant] = r.prompt; t.settings[VARIANT_FILES[r.variant][0] + '.model'] = r.model; writeTheme(t.slug, t); res.json({ ok: true }); });
/** theme test: { theme, faces: {variant: faceId}, models: [...], opts: {quality, resolution, aspect} } → one run per combination × model */
app.post('/api/test/theme', auth, (req, res) => {
  const t = readTheme(slugify(req.body.theme || '')); if (!t) return res.status(400).json({ error: 'pick a theme' });
  const models = (Array.isArray(req.body.models) ? req.body.models : []).filter(m => typeof m === 'string' && m).slice(0, 24); if (!models.length) return res.status(400).json({ error: 'tick at least one model' });
  const faces = req.body.faces || {}; const batch = 'b' + Date.now().toString(36); const out = []; const fd = foundationFor(t, req.body.foundation);
  for (const v of VARIANTS) { const prompt = (t.prompts[v] || '').trim(); const face = faces[v]; if (!prompt || !face) continue;
    for (const model of models) { const r = { id: crypto.randomBytes(6).toString('hex'), kind: 'theme', batch, theme: t.slug, themeName: t.name, variant: v, face, model, prompt, fullPrompt: withFoundation(fd, prompt), foundation: fd ? fd.name : null, moderation: t.settings.moderation || null, opts: req.body.opts || {}, createdAt: Date.now() }; enqueue(r); out.push(pubRun(r)); } }
  if (!out.length) return res.status(400).json({ error: 'nothing to run — give at least one combination a face (and make sure it has a prompt)' });
  res.json({ ok: true, batch, runs: out });
});
/** generator studio: { prompt, face, models, theme?, variant?, opts } */
app.post('/api/test/prompt', auth, (req, res) => {
  const prompt = String(req.body.prompt || '').trim(); if (!prompt) return res.status(400).json({ error: 'write a prompt' });
  const models = (Array.isArray(req.body.models) ? req.body.models : []).filter(m => typeof m === 'string' && m).slice(0, 24); if (!models.length) return res.status(400).json({ error: 'tick at least one model' });
  const batch = 'b' + Date.now().toString(36); const t = req.body.theme ? readTheme(slugify(req.body.theme)) : null; const out = [];
  const fd = foundationFor(t, req.body.foundation);
  for (const model of models) { const r = { id: crypto.randomBytes(6).toString('hex'), kind: 'studio', batch, theme: t ? t.slug : null, themeName: t ? t.name : null, variant: VARIANTS.includes(req.body.variant) ? req.body.variant : null, face: req.body.face || null, model, prompt, fullPrompt: withFoundation(fd, prompt), foundation: fd ? fd.name : null, moderation: t ? t.settings.moderation || null : null, opts: req.body.opts || {}, createdAt: Date.now() }; enqueue(r); out.push(pubRun(r)); }
  res.json({ ok: true, batch, runs: out });
});
/** matrix: { face, variant?, theme?, foundations: [id|'none'], prompts: [{label, text}], models, opts } → one run per foundation × prompt × model, all tagged with the matrix batch */
app.post('/api/test/matrix', auth, (req, res) => {
  const models = (Array.isArray(req.body.models) ? req.body.models : []).filter(m => typeof m === 'string' && m).slice(0, 24); if (!models.length) return res.status(400).json({ error: 'tick at least one model' });
  const prompts = (Array.isArray(req.body.prompts) ? req.body.prompts : []).map((p, i) => ({ label: String(p.label || 'Prompt ' + 'ABCD'[i] || i + 1).slice(0, 40), text: String(p.text || '').trim() })).filter(p => p.text).slice(0, 4); if (!prompts.length) return res.status(400).json({ error: 'write at least one prompt' });
  const s = getSettings(); const fids = (Array.isArray(req.body.foundations) ? req.body.foundations : []).map(String).slice(0, 4); if (!fids.length) return res.status(400).json({ error: 'tick at least one foundation' });
  const t = req.body.theme ? readTheme(slugify(req.body.theme)) : null; const variant = VARIANTS.includes(req.body.variant) ? req.body.variant : null;
  const quals = (Array.isArray(req.body.qualities) && req.body.qualities.length ? req.body.qualities : [(req.body.opts || {}).quality || '']).map(q => String(q || '')).slice(0, 6); const multiQ = quals.length > 1;
  const batch = 'm' + Date.now().toString(36); const out = [];
  for (const fid of fids) { const fd = fid === 'none' ? null : (s.foundations || []).find(f => f.id === fid); const fname = fid === 'none' ? 'No foundation' : fd ? fd.name : null; if (fname === null) continue;
    for (const p of prompts) for (const q of quals) for (const model of models) {
      const r = { id: crypto.randomBytes(6).toString('hex'), kind: 'matrix', batch, theme: t ? t.slug : null, themeName: t ? t.name : null, variant, face: req.body.face || null, model, prompt: p.text, promptLabel: p.label, quality: multiQ ? (q || 'default') : null, fullPrompt: withFoundation(fd && fd.text.trim() ? fd : null, p.text), foundation: fname, foundationId: fid, moderation: t ? t.settings.moderation || null : null, opts: Object.assign({}, req.body.opts || {}, { quality: q }), createdAt: Date.now() };
      enqueue(r); out.push(pubRun(r)); } }
  if (!out.length) return res.status(400).json({ error: 'no runs — check the foundations exist' });
  res.json({ ok: true, batch, runs: out });
});
app.get('/api/costs.csv', auth, (req, res) => { const rows = [...runs.values()].filter(r => r.status === 'done').sort((a, b) => a.createdAt - b.createdAt).map(r => [new Date(r.createdAt).toISOString(), r.kind, r.themeName || '', VARIANT_LABELS[r.variant] || '', r.model, r.seconds || '', r.cost != null ? r.cost.toFixed(4) : '']); const esc = v => /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v);
  const total = rows.reduce((a, r) => a + (+r[6] || 0), 0); res.setHeader('content-type', 'text/csv'); res.setHeader('content-disposition', 'attachment; filename="sketchy-lab-costs.csv"'); res.send(['when,kind,theme,combination,model,seconds,cost_usd', ...rows.map(r => r.map(esc).join(',')), '', `TOTAL,,,,,${rows.length} images,${total.toFixed(4)}`].join('\n')); });

restoreFromBucket().finally(() => { for (const id of fs.readdirSync(RUNS)) { if (!runs.has(id)) { try { const r = JSON.parse(fs.readFileSync(path.join(RUNS, id, 'run.json'), 'utf8')); if (r.status === 'processing') { r.status = 'failed'; r.error = 'server restarted mid-run'; } runs.set(r.id, r); } catch (_) {} } }
  app.listen(PORT, () => console.log(`Sketchy Lab on :${PORT} — OpenRouter key ${OR_KEY ? 'set' : 'MISSING'}, ${runs.size} saved runs`)); });
