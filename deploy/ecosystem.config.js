module.exports = {
  apps: [{
    name: 'hhg-tools-backend',
    script: 'gunicorn',
    args: '--config gunicorn.conf.py app:app',
    cwd: '/opt/hhg-tools/backend',
    interpreter: '/opt/hhg-tools/backend/venv/bin/python',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      NODE_ENV: 'production',
      FLASK_ENV: 'production'
    },
    error_file: '/opt/hhg-tools/backend/logs/err.log',
    out_file: '/opt/hhg-tools/backend/logs/out.log',
    log_file: '/opt/hhg-tools/backend/logs/combined.log',
    time: true
  }]
};
