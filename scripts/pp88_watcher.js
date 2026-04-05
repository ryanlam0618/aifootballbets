#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const mysql = require("mysql2/promise");

const DEFAULT_LIST_ENDPOINTS = ["popularRecommendPB", "getAddedOddsMatchesPB"];
const DETAIL_ENDPOINT = "getMatchDetailPB";

function asRequestTemplate(raw) {
  // Our raw_network_events schema stores a JSON blob in payload_json.
  // It can be either:
  // - { request: {...}, response: {...} }
  // - { ts, msg, code, data: "H4sI..." } (response-only)
  // - plain request-only entries
  let pj = null;
  try {
    pj = raw && raw.payload_json ? JSON.parse(String(raw.payload_json)) : null;
  } catch {
    pj = null;
  }

  const req = pj && pj.request && typeof pj.request === "object" ? pj.request : null;

  const request_url = (req && req.url) || raw.url || raw.request_url || "";
  const request_method = (req && req.method) || raw.method || raw.request_method || "GET";
  const request_headers = (req && req.headers && typeof req.headers === "object")
    ? JSON.stringify(req.headers)
    : (raw.request_headers || raw.headers || "{}");
  const request_body = (req && req.postData) || (req && req.body) || raw.payload_text || raw.request_body || "";

  // Prefer response-only payloads that contain {data:"H4sI..."} as response_body.
  const response_body = (pj && typeof pj.data === "string")
    ? JSON.stringify({ ts: pj.ts, msg: pj.msg, code: pj.code, data: pj.data })
    : (raw.response_body || raw.response || raw.response_text || "");

  return { request_url, request_method, request_headers, request_body, response_body };
}

function extractResponsePayloadFromTemplate(tpl) {
  // If we have a response body containing {data:"H4sI..."}, decode it directly (faster and avoids network).
  if (!tpl || !tpl.response_body) return null;
  let obj = null;
  try {
    obj = JSON.parse(String(tpl.response_body));
  } catch {
    return null;
  }
  if (!obj || typeof obj !== "object") return null;
  const data = obj.data;
  if (typeof data !== "string" || !data.trim().startsWith("H4sI")) return null;

  const zlib = require("zlib");
  const b64 = data.replace(/\\n/g, "\n").trim();
  try {
    const txt = zlib.gunzipSync(Buffer.from(b64, "base64")).toString("utf8");
    return parseMaybeJson(txt, null);
  } catch {
    return null;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normText(v) {
  return String(v || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function slug(v) {
  return normText(v).replace(/\s+/g, "_").slice(0, 48) || "unknown";
}

function csvEscape(v) {
  const s = String(v ?? "");
  if (/[,\"\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function requiredEnv(name) {
  const v = process.env[name];
  if (!v) throw new Error(`Missing environment variable: ${name}`);
  return v;
}

function getMysqlConfig() {
  const host = requiredEnv("DB_HOST");
  const port = Number(process.env.DB_PORT || "3306");
  const user = requiredEnv("DB_USER");
  const password = process.env.DB_PASSWORD || process.env.DB_PASS || "";
  const database = requiredEnv("DB_NAME");
  return {
    host,
    port,
    user,
    password,
    database,
    connectTimeout: Number(process.env.DB_CONNECT_TIMEOUT_MS || "5000"),
    charset: "utf8mb4",
  };
}

async function mysqlQuery(sql, params = []) {
  const cfg = getMysqlConfig();
  const conn = await mysql.createConnection(cfg);
  try {
    const [rows] = await conn.execute(sql, params);
    return rows;
  } finally {
    await conn.end();
  }
}

async function getColumns(table) {
  const db = requiredEnv("DB_NAME");
  const rows = await mysqlQuery(
    `SELECT COLUMN_NAME AS name
     FROM INFORMATION_SCHEMA.COLUMNS
     WHERE TABLE_SCHEMA=? AND TABLE_NAME=?`,
    [db, table]
  );
  return new Set(rows.map((r) => String(r.name)));
}

function pickFirst(cols, candidates) {
  for (const c of candidates) if (cols.has(c)) return c;
  return null;
}

function quoteId(id) {
  return `\`${String(id).replace(/`/g, "``")}\``;
}

async function fetchTemplatesByEndpoint(endpointKeyword, limit = 25) {
  const sql = `
SELECT url, method, payload_json, payload_text
FROM raw_network_events
WHERE url LIKE ?
ORDER BY id DESC
LIMIT ${Number(limit) || 25};
`.trim();

  const rows = await mysqlQuery(sql, [`%${endpointKeyword}%`]);
  if (!rows || rows.length === 0) return [];
  return rows.map(asRequestTemplate);
}

function parseMaybeJson(v, fallback = null) {
  try {
    return JSON.parse(v);
  } catch {
    return fallback;
  }
}

function headersFromStored(stored) {
  const h = parseMaybeJson(stored, {});
  const headers = { ...(h || {}) };
  for (const k of Object.keys(headers)) {
    const lk = k.toLowerCase();
    if (["host", "content-length", "accept-encoding", "connection"].includes(lk)) {
      delete headers[k];
    }
  }
  return headers;
}

function injectMidIntoUrl(url, mid) {
  if (!url) return url;
  let out = url;
  const midPatterns = [
    /(mid=)(\d+)/i,
    /(matchId=)(\d+)/i,
    /(match_id=)(\d+)/i,
    /(eventId=)(\d+)/i,
  ];
  for (const p of midPatterns) out = out.replace(p, `$1${mid}`);
  return out;
}

function injectMidIntoBody(body, mid) {
  if (!body) return body;

  const parsed = parseMaybeJson(body, null);
  if (parsed && typeof parsed === "object") {
    const stack = [parsed];
    while (stack.length) {
      const cur = stack.pop();
      if (!cur || typeof cur !== "object") continue;
      for (const k of Object.keys(cur)) {
        const v = cur[k];
        const nk = k.toLowerCase();
        if (["mid", "matchid", "match_id", "eventid"].includes(nk)) {
          cur[k] = Number(mid);
        } else if (v && typeof v === "object") {
          stack.push(v);
        }
      }
    }
    return JSON.stringify(parsed);
  }

  return String(body)
    .replace(/("mid"\s*:\s*)\d+/gi, `$1${mid}`)
    .replace(/("matchId"\s*:\s*)\d+/gi, `$1${mid}`)
    .replace(/("match_id"\s*:\s*)\d+/gi, `$1${mid}`)
    .replace(/([?&](?:mid|matchId|match_id|eventId)=)\d+/gi, `$1${mid}`);
}

async function replayTemplate(template, { query, mid } = {}) {
  // Fast-path: if we already have a captured (compressed) response, decode it locally.
  const decoded = extractResponsePayloadFromTemplate(template);
  if (decoded) {
    return {
      ok: true,
      status: 200,
      url: template.request_url,
      text: "",
      json: decoded,
      fromCache: true,
    };
  }

  const urlObj = new URL(template.request_url);
  if (query) {
    if (urlObj.searchParams.has("query")) urlObj.searchParams.set("query", query);
    else if (urlObj.searchParams.has("q")) urlObj.searchParams.set("q", query);
  }
  let url = urlObj.toString();
  let body = template.request_body || "";

  if (mid != null) {
    url = injectMidIntoUrl(url, mid);
    body = injectMidIntoBody(body, mid);
  }

  const method = (template.request_method || "POST").toUpperCase();
  const headers = headersFromStored(template.request_headers || "{}");

  const opts = { method, headers };
  if (method !== "GET" && body) opts.body = body;

  const res = await fetch(url, opts);
  const text = await res.text();
  return {
    ok: res.ok,
    status: res.status,
    url,
    text,
    json: parseMaybeJson(text, null),
  };
}

function walkJson(root, fn) {
  const seen = new Set();
  const stack = [root];
  while (stack.length) {
    const cur = stack.pop();
    if (!cur || typeof cur !== "object") continue;
    if (seen.has(cur)) continue;
    seen.add(cur);
    fn(cur);
    if (Array.isArray(cur)) {
      for (const it of cur) stack.push(it);
    } else {
      for (const v of Object.values(cur)) stack.push(v);
    }
  }
}

function extractMids(json) {
  const mids = new Set();
  walkJson(json, (obj) => {
    if (Array.isArray(obj)) return;
    for (const [k, v] of Object.entries(obj)) {
      const lk = k.toLowerCase();
      if (["mid", "matchid", "match_id", "eventid"].includes(lk)) {
        const n = Number(v);
        if (Number.isFinite(n) && n > 0) mids.add(n);
      }
    }
  });
  return [...mids];
}

function extractTeamPair(json) {
  let best = null;

  walkJson(json, (obj) => {
    if (Array.isArray(obj)) return;
    const entries = Object.entries(obj);
    const home = entries.find(([k, v]) => /home/i.test(k) && typeof v === "string" && v.trim());
    const away = entries.find(([k, v]) => /away/i.test(k) && typeof v === "string" && v.trim());
    if (home && away) {
      best = { home: String(home[1]), away: String(away[1]) };
      return;
    }

    if (obj.homeTeam && obj.awayTeam) {
      const h = obj.homeTeam.name || obj.homeTeam.teamName || obj.homeTeam.en || obj.homeTeam.zh;
      const a = obj.awayTeam.name || obj.awayTeam.teamName || obj.awayTeam.en || obj.awayTeam.zh;
      if (h && a) best = { home: String(h), away: String(a) };
    }
  });

  return best;
}

function teamMatches(candidate, homeNeedle, awayNeedle, query) {
  if (!candidate) return false;
  const h = normText(candidate.home);
  const a = normText(candidate.away);
  const hn = normText(homeNeedle);
  const an = normText(awayNeedle);
  const q = normText(query || "");

  const direct = h.includes(hn) && a.includes(an);
  const swapped = h.includes(an) && a.includes(hn);
  if (!(direct || swapped)) return false;
  if (!q) return true;
  return `${h} ${a}`.includes(q);
}

function extractOddsRows(json, { allMarkets = false } = {}) {
  const rows = [];
  const preferred = ["1x2", "moneyline", "asian", "handicap", "over", "under", "total"];

  walkJson(json, (obj) => {
    if (Array.isArray(obj)) return;

    const keyStr = Object.keys(obj).join(" ").toLowerCase();
    const marketName =
      obj.marketName || obj.market || obj.marketTypeName || obj.betTypeName || obj.groupName || "";

    const odd = obj.odds ?? obj.odd ?? obj.price ?? obj.value ?? obj.decimalOdds;
    if (odd != null) {
      const n = Number(odd);
      if (Number.isFinite(n) && n > 1.0) {
        const m = String(marketName || keyStr || "unknown");
        if (
          allMarkets ||
          preferred.some((kw) => m.toLowerCase().includes(kw) || keyStr.includes(kw))
        ) {
          rows.push({
            market: m,
            selection: obj.selectionName || obj.selection || obj.outcome || obj.name || "",
            line: obj.line ?? obj.handicap ?? obj.goalLine ?? obj.point ?? "",
            odds: n,
            source_key_hint: keyStr.slice(0, 120),
          });
        }
      }
    }
  });

  return rows;
}

function uniqueRows(rows) {
  const seen = new Set();
  const out = [];
  for (const r of rows) {
    const key = `${r.market}|${r.selection}|${r.line}|${r.odds}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push(r);
    }
  }
  return out;
}

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

function writeCsvReport({ rows, mid, home, away }) {
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const dir = path.join(process.cwd(), "reports", "pp88");
  ensureDir(dir);
  const file = path.join(dir, `${ts}_${slug(home)}_vs_${slug(away)}.csv`);

  const head = ["mid", "home", "away", "market", "selection", "line", "odds", "source_key_hint"];
  const lines = [head.join(",")];
  for (const r of rows) {
    lines.push(
      [mid, home, away, r.market, r.selection, r.line, r.odds, r.source_key_hint]
        .map(csvEscape)
        .join(",")
    );
  }
  fs.writeFileSync(file, `${lines.join("\n")}\n`, "utf8");
  return file;
}

async function findMidAndOdds({ homeNeedle, awayNeedle, query, allMarkets, listEndpoint }) {
  const endpoints = listEndpoint ? [String(listEndpoint)] : [...DEFAULT_LIST_ENDPOINTS];
  const mids = new Set();

  for (const ep of endpoints) {
    const templates = await fetchTemplatesByEndpoint(ep, 25);
    for (const tpl of templates) {
      try {
        const rs = await replayTemplate(tpl, { query });
        const payload = rs.json ?? parseMaybeJson(rs.text, null);
        if (!payload) continue;
        for (const m of extractMids(payload)) mids.add(m);
      } catch {
        // continue
      }
    }
  }

  if (!mids.size) return { found: false, reason: "no mids from list endpoints" };

  const detailTemplates = await fetchTemplatesByEndpoint(DETAIL_ENDPOINT, 40);
  if (!detailTemplates.length) return { found: false, reason: "no getMatchDetailPB template found" };

  for (const mid of mids) {
    for (const tpl of detailTemplates) {
      try {
        const rs = await replayTemplate(tpl, { mid });
        const payload = rs.json ?? parseMaybeJson(rs.text, null);
        if (!payload) continue;

        const team = extractTeamPair(payload);
        if (!teamMatches(team, homeNeedle, awayNeedle, query)) continue;

        const rows = uniqueRows(extractOddsRows(payload, { allMarkets }));
        return { found: true, mid, home: team.home, away: team.away, oddsRows: rows, payload };
      } catch {
        // continue
      }
    }
  }

  return { found: false, reason: "matched mid not found from detail endpoint" };
}

async function watchMatchOdds({
  homeNeedle,
  awayNeedle,
  query = "",
  intervalSec = 30,
  timeoutSec = 1800,
  once = false,
  allMarkets = false,
  listEndpoint = "",
  dryRun = false,
} = {}) {
  if (!homeNeedle || !awayNeedle) throw new Error("homeNeedle and awayNeedle are required");

  const started = Date.now();
  const intervalMs = Math.max(1, Number(intervalSec || 30)) * 1000;
  const timeoutMs = Math.max(1, Number(timeoutSec || 1800)) * 1000;

  do {
    const result = await findMidAndOdds({ homeNeedle, awayNeedle, query, allMarkets, listEndpoint });

    if (result.found) {
      const meta = {
        ok: true,
        mid: result.mid,
        home: result.home,
        away: result.away,
        oddsCount: (result.oddsRows || []).length,
      };

      if (dryRun) {
        console.log(`[pp88 dry-run] resolved MID=${result.mid} :: ${result.home} vs ${result.away}`);
        return { ...meta, dryRun: true };
      }

      if (!result.oddsRows || result.oddsRows.length === 0) {
        if (once) return { ...meta, ok: false, reason: "mid resolved but no odds rows available" };
      } else {
        const reportPath = writeCsvReport({
          rows: result.oddsRows,
          mid: result.mid,
          home: result.home,
          away: result.away,
        });
        console.log(`[pp88] report: ${reportPath}`);
        return { ...meta, reportPath };
      }
    }

    if (once) return { ok: false, reason: "not found on single pass" };

    if (Date.now() - started >= timeoutMs) return { ok: false, reason: "timeout" };

    await sleep(intervalMs);
  } while (true);
}

module.exports = {
  watchMatchOdds,
};
