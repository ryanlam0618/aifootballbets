#!/usr/bin/env node
/**
 * Decrypt OddsPortal encrypted payloads (encriptedResponse=true) using the key derivation
 * seen in the OddsPortal app bundle.
 *
 * Input: an encrypted string `e` such that atob(e) yields "<cipher_b64>:<iv_hex>".
 * Output: plaintext UTF-8 string.
 *
 * This mirrors the bundle logic:
 * - password: "J*8sQ!p$7aD_fR2yW@gHn*3bVp#sAdLd_k"
 * - salt:     "5b9a8f2c3e6d1a4b7c8e9d0f1a2b3c4d"
 * - PBKDF2 SHA-256, iterations=1000, keyLen=256
 * - AES-CBC with iv=hex
 */

import { webcrypto as crypto } from 'node:crypto';

function usage() {
  process.stderr.write(
    'Usage: node scripts/oddsportal_decrypt_match_event.js --in <encrypted_string>\n' +
      '       (or omit --in to read from stdin)\n',
  );
}

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--in') out.input = argv[++i];
    else if (a === '--help' || a === '-h') out.help = true;
    else throw new Error(`Unknown arg: ${a}`);
  }
  return out;
}

function atobNode(b64) {
  return Buffer.from(b64, 'base64').toString('binary');
}

function b64ToBytes(b64) {
  return new Uint8Array(Buffer.from(b64, 'base64'));
}

function hexToBytes(hex) {
  const clean = (hex || '').trim();
  if (!/^[0-9a-fA-F]*$/.test(clean) || clean.length % 2 !== 0) {
    throw new Error('IV hex invalid');
  }
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

async function decryptOddsPortal(encrypted) {
  const PASSWORD = 'J*8sQ!p$7aD_fR2yW@gHn*3bVp#sAdLd_k';
  const SALT = '5b9a8f2c3e6d1a4b7c8e9d0f1a2b3c4d';

  const decoded = atobNode(encrypted.trim());
  const parts = decoded.split(':');
  if (parts.length !== 2) {
    throw new Error('Encrypted payload does not decode to <b64>:<ivhex>');
  }
  const [cipherB64, ivHex] = parts;

  const iv = hexToBytes(ivHex);
  const cipherBytes = b64ToBytes(cipherB64);

  const enc = new TextEncoder();
  const baseKey = await crypto.subtle.importKey(
    'raw',
    enc.encode(PASSWORD),
    { name: 'PBKDF2' },
    false,
    ['deriveKey'],
  );

  const aesKey = await crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: enc.encode(SALT), iterations: 1000, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-CBC', length: 256 },
    false,
    ['decrypt'],
  );

  const plainBuf = await crypto.subtle.decrypt({ name: 'AES-CBC', iv }, aesKey, cipherBytes);
  return new TextDecoder().decode(plainBuf);
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    usage();
    process.exit(0);
  }

  let input = args.input;
  if (!input) {
    input = await new Promise((resolve) => {
      let d = '';
      process.stdin.setEncoding('utf8');
      process.stdin.on('data', (c) => (d += c));
      process.stdin.on('end', () => resolve(d));
    });
  }

  if (!input || !input.trim()) {
    usage();
    process.exit(2);
  }

  const plain = await decryptOddsPortal(input);
  process.stdout.write(plain);
}

main().catch((e) => {
  process.stderr.write(`${e?.message || String(e)}\n`);
  process.exit(1);
});
