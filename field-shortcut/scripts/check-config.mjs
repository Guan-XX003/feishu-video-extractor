import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const configPath = path.resolve(scriptDir, '../src/config.ts');
const config = fs.readFileSync(configPath, 'utf8');
const match = config.match(/BACKEND_URL\s*=\s*['\"]([^'\"]+)['\"]/);

if (!match) {
  throw new Error('BACKEND_URL was not found in src/config.ts');
}

const backendUrl = match[1];
if (backendUrl.includes('replace-with-your-backend.example.com')) {
  console.error('BACKEND_URL is still the migration placeholder.');
  console.error('Run ../scripts/set-backend-url.sh https://your-backend.example.com before building.');
  process.exit(1);
}

const parsed = new URL(backendUrl);
const isLocal = ['localhost', '127.0.0.1'].includes(parsed.hostname);
if (parsed.protocol !== 'https:' && !isLocal) {
  console.error('BACKEND_URL must use HTTPS except for localhost debugging.');
  process.exit(1);
}

console.log(`BACKEND_URL configuration is valid: ${backendUrl}`);
