#!/usr/bin/env node
// Measure the token cost of a single Claude Code session — main thread plus
// every sub-agent it dispatched. Companion to `mikko-skill-usage`, which
// slices the portfolio BY SKILL across all sessions; this one slices a
// single session BY WHO-SPENT-IT (main thread vs each sub-agent).
//
// Output: JSON to stdout with per-sub-agent breakdown plus totals, OR a
// human-readable summary when --format=summary is passed.
//
// The accounting convention matches mikko-skill-usage:
//   counted   = input_tokens + output_tokens + cache_creation_input_tokens
//   not counted = cache_read_input_tokens (paid upstream, ~10x cheaper, would
//                 double-bill multi-turn runs)
//
// Dedupe by `requestId` so the harness's adjacent thinking+tool_use lines
// (same requestId, same usage) don't double-count.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const args = parseArgs(process.argv.slice(2));
const PROJECTS_DIR =
  args['projects-dir'] ?? path.join(os.homedir(), '.claude', 'projects');
const PROJECT_DIR = args['project-dir'] ?? resolveProjectDir(process.cwd(), PROJECTS_DIR);
const SESSION = args['session'] ?? findLatestSession(PROJECT_DIR);
const FORMAT = args['format'] ?? 'summary';

if (!PROJECT_DIR) {
  console.error('error: no project directory matched the current cwd.');
  console.error('       tried: ' + path.join(PROJECTS_DIR, encodeCwd(process.cwd())));
  console.error('       pass --project-dir <path> explicitly to override.');
  process.exit(1);
}
if (!SESSION) {
  console.error('error: no session JSONL found in ' + PROJECT_DIR);
  process.exit(1);
}

const mainFile = path.join(PROJECT_DIR, SESSION + '.jsonl');
const subDir = path.join(PROJECT_DIR, SESSION, 'subagents');
const subFiles = fs.existsSync(subDir)
  ? fs
      .readdirSync(subDir)
      .filter((f) => f.endsWith('.jsonl'))
      .map((f) => path.join(subDir, f))
  : [];

const seen = new Set();
const main = readFile(mainFile);
const subAgents = subFiles
  .map((p) => {
    const meta = readMeta(p);
    const stats = readFile(p);
    return {
      agentId: path.basename(p).replace(/^agent-/, '').replace(/\.jsonl$/, ''),
      description: meta?.description ?? null,
      ...stats,
    };
  })
  .sort((a, b) => b.total - a.total);

const subTotals = subAgents.reduce(
  (acc, s) => ({
    in: acc.in + s.in,
    out: acc.out + s.out,
    cacheCreate: acc.cacheCreate + s.cacheCreate,
    cacheRead: acc.cacheRead + s.cacheRead,
    msgs: acc.msgs + s.msgs,
    total: acc.total + s.total,
  }),
  { in: 0, out: 0, cacheCreate: 0, cacheRead: 0, msgs: 0, total: 0 },
);

const report = {
  session: SESSION,
  project_dir: PROJECT_DIR,
  generated_at: new Date().toISOString(),
  main: main,
  sub_agents: subAgents,
  sub_agent_totals: subTotals,
  total_counted: main.total + subTotals.total,
};

if (FORMAT === 'json') {
  process.stdout.write(JSON.stringify(report, null, 2) + '\n');
} else {
  printSummary(report);
}

function readFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return { in: 0, out: 0, cacheCreate: 0, cacheRead: 0, msgs: 0, total: 0, skipped: 0 };
  }
  const lines = fs.readFileSync(filePath, 'utf8').split('\n');
  let tIn = 0,
    tOut = 0,
    tCC = 0,
    tCR = 0,
    msgs = 0,
    skipped = 0;
  for (const line of lines) {
    if (!line.trim()) continue;
    let m;
    try {
      m = JSON.parse(line);
    } catch {
      skipped++;
      continue;
    }
    if (m.type !== 'assistant') continue;
    if (!m.message?.usage) continue;
    const reqId = m.requestId || m.message?.id;
    if (reqId && seen.has(reqId)) continue;
    if (reqId) seen.add(reqId);
    const u = m.message.usage;
    tIn += u.input_tokens || 0;
    tOut += u.output_tokens || 0;
    tCC += u.cache_creation_input_tokens || 0;
    tCR += u.cache_read_input_tokens || 0;
    msgs++;
  }
  return {
    in: tIn,
    out: tOut,
    cacheCreate: tCC,
    cacheRead: tCR,
    msgs,
    total: tIn + tOut + tCC,
    skipped,
  };
}

function readMeta(jsonlPath) {
  const metaPath = jsonlPath.replace(/\.jsonl$/, '.meta.json');
  if (!fs.existsSync(metaPath)) return null;
  try {
    return JSON.parse(fs.readFileSync(metaPath, 'utf8'));
  } catch {
    return null;
  }
}

// The harness encodes <cwd> by replacing path separators and ':' with '-'.
// Single source of truth for the encoding so the resolver and the error
// message can't drift if the harness ever changes how it spells project
// directories.
function encodeCwd(cwd) {
  return cwd.replace(/[\\/]/g, '-').replace(/:/g, '-').toLowerCase();
}

function resolveProjectDir(cwd, projectsRoot) {
  // Try the encoded form first, then fall back to scanning for any dir
  // that contains a session whose entries report the same cwd.
  const encoded = encodeCwd(cwd);
  const direct = path.join(projectsRoot, encoded);
  if (fs.existsSync(direct)) return direct;
  // Try a relaxed prefix match in case the harness encoding differs in
  // edge cases (e.g. trailing-slash handling on Windows).
  if (!fs.existsSync(projectsRoot)) return null;
  const candidates = fs
    .readdirSync(projectsRoot)
    .filter((d) => encoded.endsWith(d.toLowerCase()) || d.toLowerCase().endsWith(encoded));
  if (candidates.length === 1) return path.join(projectsRoot, candidates[0]);
  return null;
}

function findLatestSession(projectDir) {
  if (!projectDir || !fs.existsSync(projectDir)) return null;
  const entries = fs
    .readdirSync(projectDir, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith('.jsonl'))
    .map((e) => {
      const full = path.join(projectDir, e.name);
      return { name: e.name.replace(/\.jsonl$/, ''), mtime: fs.statSync(full).mtimeMs };
    })
    .sort((a, b) => b.mtime - a.mtime);
  return entries[0]?.name ?? null;
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const eq = a.indexOf('=');
    if (eq >= 0) {
      out[a.slice(2, eq)] = a.slice(eq + 1);
    } else if (argv[i + 1] && !argv[i + 1].startsWith('--')) {
      out[a.slice(2)] = argv[++i];
    } else {
      out[a.slice(2)] = true;
    }
  }
  return out;
}

function fmt(n) {
  return n.toLocaleString('en-US');
}

function printSummary(r) {
  const s = r.session.slice(0, 8) + '…';
  console.log('=== Session ' + s + ' ===');
  console.log('Project: ' + r.project_dir);
  console.log('');
  console.log(
    'Main thread:  ' +
      fmt(r.main.total) +
      ' tokens (' +
      r.main.msgs +
      ' assistant messages; ' +
      fmt(r.main.cacheRead) +
      ' served from cache)',
  );
  console.log('  input:        ' + fmt(r.main.in));
  console.log('  output:       ' + fmt(r.main.out));
  console.log('  cache create: ' + fmt(r.main.cacheCreate));
  console.log('');
  console.log(
    'Sub-agents:   ' +
      fmt(r.sub_agent_totals.total) +
      ' tokens (' +
      r.sub_agents.length +
      ' agents, ' +
      r.sub_agent_totals.msgs +
      ' assistant messages; ' +
      fmt(r.sub_agent_totals.cacheRead) +
      ' served from cache)',
  );
  console.log('  input:        ' + fmt(r.sub_agent_totals.in));
  console.log('  output:       ' + fmt(r.sub_agent_totals.out));
  console.log('  cache create: ' + fmt(r.sub_agent_totals.cacheCreate));
  console.log('');
  console.log('TOTAL counted: ' + fmt(r.total_counted) + ' tokens');
  console.log('');
  if (r.sub_agents.length > 0) {
    console.log('=== Per sub-agent (sorted by cost) ===');
    for (const sa of r.sub_agents) {
      const id = sa.agentId.slice(0, 12);
      const desc = sa.description ? ' — ' + sa.description : '';
      console.log(
        id +
          '  total=' +
          fmt(sa.total).padStart(8) +
          '  msgs=' +
          String(sa.msgs).padStart(3) +
          desc,
      );
    }
  }
}
