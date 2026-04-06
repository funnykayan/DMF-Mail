module.exports = {
  apps: [
    {
      name: 'dmf-mail-frontend',
      script: './server.js',
      cwd: __dirname,
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      watch: false,
      max_memory_restart: '256M',
      env: {
        NODE_ENV: 'production',
        PORT: 4006,
        API_URL: 'http://127.0.0.1:4007',
      },
    },
  ],
};
