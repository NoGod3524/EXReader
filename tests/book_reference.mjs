// SPDX-License-Identifier: MIT
// Execute an externally supplied, pinned Foliate source as a test oracle only.
// No reference parser code is vendored or linked into the engine.
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
const [reference, input, output] = process.argv.slice(2);
const source = await fs.readFile(reference, 'utf8');
const { decompressPalmDOC, huffcdic } = await import('data:text/javascript;base64,' +
    Buffer.from(source + '\nexport { decompressPalmDOC, huffcdic };').toString('base64'));
const data = await fs.readFile(input), records = [];
const count = data.readUInt16BE(76);
for (let i = 0; i < count; i++) records.push(data.subarray(data.readUInt32BE(78 + i * 8),
    i + 1 < count ? data.readUInt32BE(86 + i * 8) : data.length));
const h = records[0], compression = h.readUInt16BE(0), flags = h.readUInt16BE(242);
const decompress = compression === 2 ? decompressPalmDOC : compression === 17480
    ? await huffcdic({ huffcdic: h.readUInt32BE(112), numHuffcdic: h.readUInt32BE(116) },
        async i => Uint8Array.from(records[i]).buffer) : x => x;
const chunks = [];
for (let i = 1; i <= h.readUInt16BE(8); i++) {
    let r = records[i];
    for (let bit = 1; bit < 16; bit++) if (flags & (1 << bit)) {
        let length = 0, used = 0, byte;
        do { byte = r[r.length - 1 - used]; length += (byte & 127) * 2 ** (used++ * 7); } while (!(byte & 128));
        r = r.subarray(0, r.length - length);
    }
    if (flags & 1) r = r.subarray(0, r.length - (r[r.length - 1] & 3) - 1);
    chunks.push(Buffer.from(decompress(r)));
}
const raw = Buffer.concat(chunks);
await fs.writeFile(output, raw);
console.log(JSON.stringify({ compression, declared_bytes: h.readUInt32BE(4), decoded_bytes: raw.length,
    record_bytes: chunks.map(x => x.length), sha256: crypto.createHash('sha256').update(raw).digest('hex') }));
