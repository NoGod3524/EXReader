import { cp } from 'node:fs/promises';
const output = process.argv[2] || 'dist';
for (const file of ['LICENSE', 'THIRD_PARTY_NOTICES.md']) await cp(file, `${output}/${file}`);
await cp('src/render.css', `${output}/render.css`);
