#!/usr/bin/env node
"use strict";

function parseMaybeJson(v) {
  try {
    return JSON.parse(v);
  } catch {
    return null;
  }
}

function gunzipBase64(b64) {
  const zlib = require("zlib");
  const buf = Buffer.from(String(b64 || ""), "base64");
  const out = zlib.gunzipSync(buf);
  return out.toString("utf8");
}

function unescapeNewlines(s) {
  return String(s || "").replace(/\\n/g, "\n");
}

const input = process.argv[2] || "";
const obj = parseMaybeJson(input);
if (!obj) {
  console.error("not json");
  process.exit(1);
}

let b64 = null;
if (typeof obj.data === "string" && obj.data.trim().startsWith("H4sI")) {
  b64 = unescapeNewlines(obj.data.trim());
} else if (obj.response && typeof obj.response === "object") {
  if (typeof obj.response.body === "string" && obj.response.body.trim().startsWith("H4sI")) {
    b64 = unescapeNewlines(obj.response.body.trim());
  }
}

if (!b64) {
  console.log(JSON.stringify(obj, null, 2));
  process.exit(0);
}

try {
  const txt = gunzipBase64(b64);
  const j = parseMaybeJson(txt);
  if (j) console.log(JSON.stringify(j, null, 2));
  else console.log(txt);
} catch (e) {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(2);
}
