#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const root = path.resolve(process.argv[2] || "public");
const walk = (dir) =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? walk(path.join(dir, entry.name)) : [path.join(dir, entry.name)],
  );

if (!fs.existsSync(root)) throw new Error(`missing public root: ${root}`);
const files = walk(root);
const htmlFiles = files.filter((file) => file.endsWith(".html"));
if (!htmlFiles.some((file) => path.basename(file) === "index.html")) {
  throw new Error("missing index.html");
}

const forbidden = [
  [/\bRPA Library\b/i, "legacy brand"],
  [/rpallibrary/i, "legacy internal name"],
  [/Processing receipt/i, "processing receipt"],
  [/provenance ledger/i, "provenance ledger"],
  [/\bBatch ID\b/i, "batch ID"],
  [/\bUID\s*:?\s*\d+/i, "message UID"],
  [/\bNews ID\s*:/i, "news ID"],
  [/America\/Chicago/i, "internal timezone"],
  [/(?:^|[\s"'=])[A-Z]:[\\/]/im, "Windows path"],
  [/\/home\//i, "home path"],
  [/\/mnt\/[a-z]\//i, "WSL path"],
  [/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/, "email address"],
];

const errors = [];
for (const file of htmlFiles) {
  const rel = path.relative(root, file).replaceAll("\\", "/");
  const source = fs.readFileSync(file, "utf8");
  for (const [pattern, name] of forbidden) {
    if (pattern.test(source)) errors.push(`${rel}: ${name}`);
  }
  if (/<script\b/i.test(source)) errors.push(`${rel}: script tag`);
  if (/<(?:img|iframe|video|audio|source)\b[^>]+src=["']https?:/i.test(source) || /<link\b[^>]*rel=["']stylesheet["'][^>]*href=["']https?:/i.test(source)) {
    errors.push(`${rel}: remote asset`);
  }
  if (rel !== "404.html") {
    if (!/<meta name="description"/i.test(source)) {
      errors.push(`${rel}: missing description`);
    }
    if (!/<link rel="canonical" href="https:\/\/themorningcommit\.com\//i.test(source)) {
      errors.push(`${rel}: missing canonical`);
    }
    if (!/<meta property="og:title"/i.test(source)) {
      errors.push(`${rel}: missing Open Graph title`);
    }
  }
  if (/data-style-system="themorningcommit"/i.test(source)) {
    const tabs = (source.match(/<input\b[^>]*name="brief-tab"/gi) || []).length;
    if (tabs !== 7) errors.push(`${rel}: expected 7 tabs, found ${tabs}`);
    const facts = [
      ...source.matchAll(
        /<(?:article|li|tr)\b[^>]*(?:class="[^"]*fact-item|data-fact-item="true")[^>]*>([\s\S]*?)<\/(?:article|li|tr)>/gi,
      ),
    ];
    for (const fact of facts) {
      if (!/<a\b[^>]*class="[^"]*source-link[^>]*target="_blank"[^>]*rel="noopener noreferrer"/i.test(fact[0])) {
        errors.push(`${rel}: factual item missing safe direct source link`);
      }
    }
  }
}

for (const file of files) {
  const rel = path.relative(root, file).replaceAll("\\", "/");
  if (/\.(?:json|env|log|db|sqlite)$/i.test(rel)) {
    errors.push(`${rel}: forbidden private file type`);
  }
}

if (errors.length) {
  console.error(JSON.stringify({ status: "fail", errors }, null, 2));
  process.exit(1);
}
console.log(
  JSON.stringify(
    { status: "pass", root, files: files.length, html: htmlFiles.length },
    null,
    2,
  ),
);
