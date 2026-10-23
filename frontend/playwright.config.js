import {defineConfig} from '@playwright/test';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {tmpdir} from 'node:os';

const localPython = fileURLToPath(new URL(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python', import.meta.url));
const python = process.env.SENTINELOPS_PYTHON || (existsSync(localPython) ? localPython : 'python');
export default defineConfig({
  testDir: 'e2e', workers: 2,
  use: {baseURL:'http://127.0.0.1:5173', screenshot:'only-on-failure', trace:'retain-on-failure'},
  reporter: [['list'], ['html', {open:'never'}]],
  webServer: [
    {command:`"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000`, cwd:'../backend', url:'http://127.0.0.1:8000/docs', reuseExistingServer:false,
      env:{SENTINELOPS_DB:join(tmpdir(), `sentinelops-e2e-${process.pid}.db`)}},
    {command:'npm run dev -- --host 127.0.0.1 --strictPort', url:'http://127.0.0.1:5173', reuseExistingServer:false}
  ]
});
