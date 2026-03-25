#!/usr/bin/env node
"use strict";

const { watchMatchOdds } = require("./pp88_watcher");

function envBool(name, def = false) {
  const v = process.env[name];
  if (v == null || v === "") return def;
  return ["1", "true", "yes", "y", "on"].includes(String(v).toLowerCase());
}

function envNum(name, def) {
  const v = process.env[name];
  if (v == null || v === "") return def;
  const n = Number(v);
  return Number.isFinite(n) ? n : def;
}

async function main() {
  const homeNeedle = process.env.HOME_NEEDLE || "";
  const awayNeedle = process.env.AWAY_NEEDLE || "";
  if (!homeNeedle || !awayNeedle) {
    console.error("HOME_NEEDLE and AWAY_NEEDLE are required");
    process.exit(2);
  }

  const result = await watchMatchOdds({
    homeNeedle,
    awayNeedle,
    query: process.env.QUERY || "",
    intervalSec: envNum("INTERVAL_SEC", 30),
    timeoutSec: envNum("TIMEOUT_SEC", 1800),
    once: envBool("ONCE", false),
    allMarkets: envBool("ALL_MARKETS", false),
    listEndpoint: process.env.LIST_ENDPOINT || "",
    dryRun: envBool("DRY_RUN", false),
  });

  console.log(JSON.stringify(result, null, 2));
  process.exit(result && result.ok ? 0 : 1);
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
