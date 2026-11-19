const express = require('express');
const cors = require('cors');
const path = require('path');
const crypto = require('crypto');
const fs = require('fs');

// 导入网易云音乐 API
const NCM = require('NeteaseCloudMusicApi');

const app = express();
const PORT = process.env.PORT || 3000;

// CORS 已在 Express 5 默认启用

// Cookie 存储（文件持久化，重启不丢）
const COOKIE_STORE = new Map();
const COOKIE_FILE = path.join(__dirname, '.cookies.json');

// 启动时读文件
try {
  if (fs.existsSync(COOKIE_FILE)) {
    const saved = JSON.parse(fs.readFileSync(COOKIE_FILE, 'utf8'));
    Object.entries(saved).forEach(([k, v]) => COOKIE_STORE.set(k, v));
    console.log(`[啟動] 載入 ${COOKIE_STORE.size} 個登入 session`);
  }
} catch {}

// 保存 cookie 到文件（防抖）
let saveTimer = null;
function saveCookies() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try {
      const obj = {};
      COOKIE_STORE.forEach((v, k) => obj[k] = v);
      fs.writeFileSync(COOKIE_FILE, JSON.stringify(obj));
    } catch {}
  }, 500);
}

// 中间件
app.use(cors({
  origin: true,
  credentials: true,
  exposedHeaders: ['Set-Cookie']
}));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// 静态文件
app.use(express.static(path.join(__dirname, 'public')));

// ====== 自动注册所有 NeteaseCloudMusicApi 路由 ======
const apiFunctions = Object.entries(NCM).filter(([name, fn]) => {
  return typeof fn === 'function' && name !== 'server' && name !== 'getModulesDefinitions';
});

// 辅助：函数名转路由路径  login_cellphone -> /api/login/cellphone
function nameToPath(name) {
  return '/api/' + name.replace(/_/g, '/');
}

apiFunctions.forEach(([name, fn]) => {
  const routePath = nameToPath(name);

  app.all(routePath, async (req, res) => {
    try {
      // 合并 query 和 body 参数
      const params = { ...req.query, ...req.body };

      // 注入 cookie（如果有）
      const sid = req.headers.cookie?.match(/sid=([^;]+)/)?.[1];
      if (sid && COOKIE_STORE.has(sid)) {
        params.cookie = COOKIE_STORE.get(sid);
      }

      // 注入 realIP（避免IP限制）
      if (!params.realIP) params.realIP = '116.25.140.98';

      // 调用 API 函数
      const result = await fn(params);

      // ====== 統一 cookie 處理（支持 QR check 的 body.cookie）======
      // 可能的位置: result.cookie (數組), result.body.cookie (字符串)
      let rawCookie = null;
      if (result.cookie && Array.isArray(result.cookie) && result.cookie.length) {
        rawCookie = result.cookie.join(';');
      } else if (result.body?.cookie) {
        rawCookie = result.body.cookie;
      }

      if (rawCookie) {
        let sessionId = sid && COOKIE_STORE.has(sid) ? sid : crypto.randomBytes(8).toString('hex');
        COOKIE_STORE.set(sessionId, rawCookie);
        saveCookies();
        res.cookie('sid', sessionId, {
          httpOnly: false, sameSite: 'lax', path: '/',
          maxAge: 7 * 24 * 3600 * 1000
        });
      }

      // 直接返回 body 内容（前端无需再处理 status/body 层级）
      const body = result.body || result;
      res.json(body);
    } catch (err) {
      console.error(`[API ${name}]`, err);
      // 透傳網易雲原始錯誤碼（-462/503/509 等），不要一律包成 500
      const body = err.body || err.data || { code: -1, message: err.message };

      // ====== catch 裡也處理 cookie！（QR check 失敗時可能有 cookie）======
      let errCookie = null;
      if (err.cookie && Array.isArray(err.cookie) && err.cookie.length) {
        errCookie = err.cookie.join(';');
      } else if (body.cookie && typeof body.cookie === 'string') {
        errCookie = body.cookie;
      } else if (body.data?.cookie) {
        errCookie = body.data.cookie;
      }
      if (errCookie) {
        let sessionId = sid && COOKIE_STORE.has(sid) ? sid : crypto.randomBytes(8).toString('hex');
        COOKIE_STORE.set(sessionId, errCookie);
        saveCookies();
        res.cookie('sid', sessionId, { httpOnly: false, sameSite: 'lax', path: '/', maxAge: 7 * 24 * 3600 * 1000 });
      }

      res.status(200).json(body);
    }
  });
});

// ====== 辅助路由 ======
app.get('/api/ping', (req, res) => {
  res.json({ status: 'ok', message: '网易云音乐服务运行中', apis: apiFunctions.length });
});

// 退出登录时清除 cookie
app.get('/api/logout', async (req, res) => {
  const sid = req.headers.cookie?.match(/sid=([^;]+)/)?.[1];
  if (sid) { COOKIE_STORE.delete(sid); saveCookies(); }
  res.clearCookie('sid');
  res.json({ code: 200, message: '退出成功' });
});

// ====== 启动服务器 ======
const server = app.listen(PORT, '0.0.0.0', () => {
  console.log('========================================');
  console.log(' 🎵 AdiPlayer - 服务已启动');
  console.log(` 📍 本地访问: http://localhost:${PORT}`);
  console.log(` 🔌 已注册 ${apiFunctions.length} 个 API 接口`);
  console.log('========================================');
});
server.keepAliveTimeout = 120000;
server.headersTimeout = 120000;
// 保持進程活動
const heartbeat = setInterval(() => {
  if (server.listening) { /* still alive */ }
}, 30000);
process.on('exit', () => clearInterval(heartbeat));
process.on('SIGINT', () => { clearInterval(heartbeat); server.close(); process.exit(0); });
process.on('SIGTERM', () => { clearInterval(heartbeat); server.close(); process.exit(0); });
