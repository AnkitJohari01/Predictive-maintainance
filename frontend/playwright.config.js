import {defineConfig} from "@playwright/test";
import {resolve} from "node:path";
import {tmpdir} from "node:os";
const python=process.env.SENTINELOPS_PYTHON||"python";
export default defineConfig({testDir:"e2e",workers:2,use:{baseURL:"http://127.0.0.1:5173",trace:"retain-on-failure"},
  webServer:[{command:`"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,cwd:resolve("../backend"),url:"http://127.0.0.1:8000/docs",reuseExistingServer:false,
              env:{SENTINELOPS_DB:resolve(tmpdir(),`sentinelops-e2e-${process.pid}.sqlite`)}},
             {command:`"${process.execPath}" "${resolve("node_modules/vite/bin/vite.js")}" --host 127.0.0.1 --port 5173 --strictPort`,url:"http://127.0.0.1:5173",reuseExistingServer:false}]});
