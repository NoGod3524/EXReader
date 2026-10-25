// Exact GitHub slugger, including Chinese punctuation and duplicate headings.
import fs from 'node:fs';
const {default: GithubSlugger} = await import(process.env.SLUGGER_MODULE);
const slugger = new GithubSlugger();
const headings = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(headings.map(x => slugger.slug(x))));
