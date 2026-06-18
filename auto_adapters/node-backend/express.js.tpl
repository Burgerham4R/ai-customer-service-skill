// routes/voice-agent.js  (Express)
// 由 conversation-core/auto_adapters/node-backend 自动生成。
// 反代用户请求到骨架进程，避免前端直接暴露骨架地址。
const express = require('express');
const fetch = (...args) => import('node-fetch').then(({ default: f }) => f(...args));

const SKELETON_BASE_URL = process.env.SKELETON_BASE_URL || '${SKELETON_BASE_URL}';
const API_PREFIX = process.env.API_PREFIX || '${API_PREFIX}';

const router = express.Router();
router.use(express.json({ limit: '64kb' }));

// 安全：禁止反向代理指向内网（与全局 SSRF 防护对齐）
function isPrivate(host) {
  if (!host) return false;
  const blocks = [/^10\./, /^192\.168\./, /^172\.(1[6-9]|2\d|3[0-1])\./, /^9\./, /^11\./, /^21\./, /^30\./, /^127\./];
  return blocks.some((re) => re.test(host));
}

const target = new URL(SKELETON_BASE_URL);
if (isPrivate(target.hostname) && process.env.NODE_ENV !== 'development') {
  console.warn('[voice-agent] WARNING: SKELETON_BASE_URL points to a private network');
}

router.all('*', async (req, res) => {
  const url = SKELETON_BASE_URL + API_PREFIX + req.path;
  try {
    const resp = await fetch(url, {
      method: req.method,
      headers: { 'Content-Type': 'application/json' },
      body: ['GET', 'HEAD'].includes(req.method) ? undefined : JSON.stringify(req.body || {}),
    });
    const text = await resp.text();
    res.status(resp.status).type(resp.headers.get('content-type') || 'application/json').send(text);
  } catch (err) {
    res.status(502).json({ code: 'bad_gateway', message: err.message });
  }
});

module.exports = router;
