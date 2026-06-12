/**
 * TestHub 生产环境预览服务器
 * 同时提供前端静态文件服务和后端 API 代理
 * 
 * 使用方式: node serve-prod.js
 * 
 * 功能:
 * - 静态文件服务 (dist 目录)
 * - SPA 路由回退 (所有非文件请求返回 index.html)
 * - API 请求代理到 Django 后端 (http://127.0.0.1:8000)
 * - WebSocket 代理支持
 */

const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const compression = require('compression');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

// ============ Gzip 压缩（隧道访问关键优化）============
app.use(compression());

// ============ API 代理配置 ============
// 注意：代理必须放在静态文件之前，否则会被 SPA 回退拦截
// 
// 关键：不可以使用 app.use('/api', proxy) 这种 Express 路径挂载，
// 因为 Express 会剥离 /api 前缀，导致 Django 收到错误路径 /auth/captcha/
// 而非 /api/auth/captcha/。必须使用 pathFilter 保留完整原始 URL。

const apiProxy = createProxyMiddleware({
  target: BACKEND_URL,
  changeOrigin: true,
  secure: false,
  pathFilter: [
    '/api/**',
    '/media/**',
    '/app-automation-templates/**',
    '/app-automation-reports/**',
  ],
  onError: (err, req, res) => {
    console.error(`[Proxy Error] ${req.url}: ${err.message}`);
    res.status(502).json({ error: '代理服务不可用', detail: err.message });
  },
});

app.use(apiProxy);

// WebSocket 代理
const wsProxy = createProxyMiddleware({
  target: BACKEND_URL,
  changeOrigin: true,
  ws: true,
  secure: false,
  pathFilter: ['/ws/**'],
});
app.use(wsProxy);

// ============ 静态文件服务 ============
const distPath = path.join(__dirname, 'dist');
app.use(express.static(distPath, {
  setHeaders: (res) => {
    // 禁用缓存，方便测试
    res.set('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.set('Pragma', 'no-cache');
    res.set('Expires', '0');
  },
}));

// ============ SPA 路由回退 ============
// 所有非文件请求返回 index.html（支持 Vue Router history 模式）
app.get('*', (req, res, next) => {
  // 跳过 API 等代理路径
  if (req.path.startsWith('/api/') || 
      req.path.startsWith('/media/') || 
      req.path.startsWith('/ws/') ||
      req.path.startsWith('/app-automation-')) {
    return next();
  }
  res.sendFile(path.join(distPath, 'index.html'));
});

// ============ 启动服务器 ============
const server = app.listen(PORT, () => {
  console.log('');
  console.log('  ============================================');
  console.log(`  TestHub 生产环境预览服务器`);
  console.log(`  ============================================`);
  console.log(`  前端地址: http://localhost:${PORT}`);
  console.log(`  API 代理目标: ${BACKEND_URL}`);
  console.log(`  ============================================`);
  console.log('');
  console.log('  确保 Django 后端已在端口 8000 上运行:');
  console.log('  python manage.py runserver');
  console.log('');
});

// WebSocket 升级处理
server.on('upgrade', (req, socket, head) => {
  if (req.url.startsWith('/ws/')) {
    wsProxy.upgrade(req, socket, head);
  }
});
