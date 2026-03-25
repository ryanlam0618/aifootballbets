#!/usr/bin/env node

const fs = require('node:fs');

function parseArgs(argv) {
  const out = { timeoutMs: 20000 };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--url') {
      out.url = argv[++i];
    } else if (a === '--out') {
      out.out = argv[++i];
    } else if (a === '--timeout-ms') {
      out.timeoutMs = Number(argv[++i] || 20000);
    } else if (a === '--help' || a === '-h') {
      out.help = true;
    } else {
      throw new Error(`Unknown argument: ${a}`);
    }
  }
  return out;
}

function usage() {
  process.stderr.write(
    'Usage: node scripts/sofascore_fetch.js --url <url> [--out <path>] [--timeout-ms <ms>]\\n',
  );
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help || !args.url) {
    usage();
    process.exit(args.help ? 0 : 2);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new Error('timeout')), Math.max(1000, args.timeoutMs || 20000));

  let res;
  try {
    res = await fetch(args.url, {
      method: 'GET',
      headers: {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
        Accept: 'application/json,text/plain,*/*',
      },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }

  const body = await res.text();

  if (!res.ok) {
    if (body) {
      process.stderr.write(body.slice(0, 500));
      process.stderr.write('\n');
    }
    process.stderr.write(`HTTP ${res.status} for ${args.url}\n`);
    process.exit(1);
  }

  if (args.out) {
    fs.writeFileSync(args.out, body, 'utf8');
  } else {
    process.stdout.write(body);
  }
}

main().catch((err) => {
  process.stderr.write(`${err?.message || String(err)}\n`);
  process.exit(1);
});
