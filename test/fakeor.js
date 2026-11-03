// pretend OpenRouter on :9996 — lists a few image models, returns the input face (or a blank) as the "generated" PNG
const http = require('http'); const fs = require('fs'); const face = fs.readFileSync(process.argv[2]);
const MODELS = [{ id: 'openai/gpt-image-1', name: 'OpenAI: GPT Image 1', supported_parameters: ['input_references', 'quality', 'size'], pricing: { image: '0.04' } }, { id: 'google/gemini-3.1-flash-image-preview', name: 'Google: Gemini 3.1 Flash Image', supported_parameters: ['input_references', 'aspect_ratio'], pricing: { image: '0.03' } }, { id: 'black-forest-labs/flux.2-pro', name: 'BFL: FLUX.2 Pro', supported_parameters: ['input_references', 'resolution', 'aspect_ratio'] }, { id: 'acme/text-only-image', name: 'Acme text-only', supported_parameters: ['aspect_ratio'] }];
http.createServer((req, res) => { let b = ''; req.on('data', c => b += c); req.on('end', () => { const json = (c, o) => { res.writeHead(c, { 'content-type': 'application/json' }); res.end(JSON.stringify(o)); };
  if (!/^Bearer /.test(req.headers.authorization || '')) return json(401, { error: { message: 'no key' } });
  if (req.url.startsWith('/api/v1/images/models')) return json(200, { data: MODELS });
  if (req.url.startsWith('/api/v1/key')) return json(200, { data: { label: 'lab key', usage: 1.23, limit: null, limit_remaining: null } });
  if (req.url === '/api/v1/images' && req.method === 'POST') { const body = JSON.parse(b); console.log('image', body.model, 'refs:', (body.input_references || []).length, 'q:', body.quality, 'r:', body.resolution, 'a:', body.aspect_ratio);
    if (body.model === 'google/gemini-3.1-flash-image-preview' && body.quality) return json(400, { error: { message: 'Unsupported parameter: quality' } });
    if (/REFUSEME/.test(body.prompt)) return json(400, { error: { message: 'content moderation blocked this request' } });
    return setTimeout(() => json(200, { created: Date.now() / 1000 | 0, data: [{ b64_json: face.toString('base64') }], usage: { prompt_tokens: 0, completion_tokens: 100, total_tokens: 100, cost: 0.042 } }), 800); }
  json(404, { error: { message: 'unknown ' + req.url } }); }); }).listen(9996, () => console.log('fake openrouter on 9996'));
