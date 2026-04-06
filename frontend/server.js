const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 4006;
const API_URL = process.env.API_URL || 'http://127.0.0.1:4007';

// Proxy /api/* → Python FastAPI backend
app.use(
  '/api',
  createProxyMiddleware({
    target: API_URL,
    changeOrigin: true,
    logLevel: 'warn',
  })
);

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// SPA fallback – send index.html for any unknown route
app.get('*', (_req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`DMF Mail frontend running on http://0.0.0.0:${PORT}`);
  console.log(`Proxying /api/* → ${API_URL}`);
});
