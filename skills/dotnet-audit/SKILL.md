---
name: dotnet-audit
description: Read-only audit for ASP.NET Core / EF Core / C# anti-patterns that generic audits miss — captive DI dependencies, untracked-vs-tracked EF queries, missing CancellationToken, DbContext concurrency, sync-over-async, @Html.Raw XSS, overposting, open redirects, swallowed exceptions (incl. cancellation). Five parallel subagents over non-overlapping .NET scopes; each check pairs a smell with a legitimate counter-example. Runs a pre-flight fit check first — aborts cleanly if the codebase isn't .NET. Writes severity-ranked results to docs/audits/dotnet-<date>.md. Use for "audit my .NET code", "review this ASP.NET Core app", "check my EF Core usage", "find DI / async bugs", or before merging a substantial C# PR.
barney: Checks your ASP.NET Core / EF Core code for the gotchas generic audits skip — captive DI singletons, untracked queries, missing CancellationToken, sync-over-async deadlocks, @Html.Raw XSS, open redirects. Five reviewers run in parallel; every finding has a concrete counter-example. Bails fast if it's not a .NET codebase.
---

# dotnet-audit

Reads a .NET codebase (or a specified directory / branch diff) looking for anti-patterns specific to **ASP.NET Core, EF Core, and idiomatic C#**. Reports findings in a markdown report under `docs/audits/`. **Does not modify code.** The human decides which findings are real.

## Why this skill exists separately from `audit` / `ai-codegen-smell-audit`

The general audits in this library catch language-agnostic concerns — robustness bugs (`audit`), LLM-codegen surface texture (`ai-codegen-smell-audit`). Neither systematically flags **.NET-shaped** hazards: a singleton service whose constructor takes a `DbContext` looks fine to a generic auditor, but it's a captive-dependency bug that pins one scoped context for the life of the process. A `.Result` on a `Task` reads as ordinary code, yet on a request thread it can deadlock. `@Html.Raw(model.Description)` is invisible to a robustness pass but is a stored-XSS hole if the description is third-party HTML.

This skill is the **.NET-specific reviewer** — the backend analogue of `react-anti-patterns-audit`. Its checks would be noise on a Python or Go codebase, signal on an ASP.NET Core one. It is the third lens, not a replacement: run `audit` for robustness and `ai-codegen-smell-audit` for codegen texture; run **this** for the framework-specific shapes those two don't frame.

## Pre-flight check — IS THIS EVEN A .NET CODEBASE?

**Before doing anything else, the skill verifies the target looks like .NET.** If it doesn't, it aborts cleanly with a one-line message and a pointer to a more appropriate skill, rather than burning tokens on a fruitless audit.

Procedure (single main-thread pass, ~3K tokens total):

1. **`Glob` for `*.csproj` / `*.fsproj` / `*.sln`** under the target. Also note `global.json`, `Directory.Build.props` if present.
2. **`Glob` for `*.cs` files** (exclude `obj/` and `bin/` — those are generated) and count them. **`Glob` for `*.cshtml` / `*.razor`** to detect the web surface (ASP.NET Core Razor Pages / MVC / Blazor).
3. **Apply this decision matrix:**

| `.csproj`/`.sln` present? | hand-written `.cs` files? | Verdict | Action |
| --- | --- | --- | --- |
| Yes | Many (≥10) | **Proceed** | Run the full audit. If no `.cshtml`/`.razor`, skip the web-surface subagent (group D) and say so. |
| Yes | Few (1–9) | **Proceed with note** | Run the full audit; preface report with "small .NET surface — patterns may not surface at scale". |
| Yes | None (only generated) | **Bail** | "found a project file but no hand-written .cs — is the source tree elsewhere? Pass `--source <path>`." |
| No | Many | **Bail** | "found C# files but no .csproj/.sln — confirm this is the right directory, or pass `--source <path>`." |
| No | None | **Bail** | "this does not look like a .NET codebase. Try `/mikko-audit` (universal robustness) or `/mikko-ai-codegen-smell-audit` (universal LLM-codegen smells) instead." |

The pre-flight runs synchronously and outputs one of:

- `pre-flight: .NET codebase confirmed (N .csproj, M hand-written .cs files, web surface: yes/no). Proceeding with the full audit.`
- `pre-flight: aborting — <reason>. Suggested alternative: <skill-name>.`

If the pre-flight bails, **no audit runs and no report is written**. Recover by pointing at the right source tree (`--source <path>`) or invoking the suggested alternative.

Why this matters: a .NET-shaped audit run on a Django codebase still produces a report — a useless one where no check fires — after spending ~30K+ tokens to confirm "nothing here." The pre-flight short-circuits that for ~3K.

## When to invoke

- "audit my .NET / C# / ASP.NET Core code", "review this EF Core usage", "check my DI lifetimes", "find async/await bugs", "audit this C# PR"
- Before merging a substantial backend PR (new services, new EF queries, new pages/controllers)
- On a codebase ported or scaffolded by an LLM (the EF/DI/async idioms are exactly where transliteration shows)
- After running `audit` (robustness) and `ai-codegen-smell-audit` (codegen texture) — this is the *framework-specific* layer

## When NOT to invoke

- **Not** on a non-.NET codebase. The pre-flight will catch it — don't burn the cycles.
- **Not** as a substitute for `audit`. This finds .NET-shape issues, not generic robustness bugs. Run both if you want both.
- **Not** during initial code generation. Same reasoning as the other audits: the model would chase its own tail. Run after the diff exists and is ready for review.
- **Not** as a style linter. Brace placement, `var` vs explicit type, `this.` usage — that's `dotnet format` / EditorConfig / analyzers. This skill targets shapes those don't catch.
- **Not** an "is this idiomatic" vibe check. It checks **shapes** (concrete patterns with verifiable consequences), not taste.

## What this skill does NOT do

- **Does not modify code.** Output is a markdown report; the human picks fixes.
- **Does not flag a pattern that's documented or immunised.** A `// audit:dotnet:ignore <check> — <reason>` comment on the line, or a documented invariant in `CLAUDE.md`, immunises it (see **Calibration rules**).
- **Does not re-report what the build already enforces.** Nullable-reference warnings, unused usings, analyzer diagnostics — if the project runs analyzers as errors, those are the build's job; this skill notes the build config and moves on.
- **Does not grade architecture.** "This should be a separate project / use MediatR / CQRS" is out of scope. It audits patterns, not whether the pattern should exist.

## Token economy — deterministic before dispatch

The cost of an audit is the subagent pass; everything else is cheap. So **everything that ripgrep, the .NET SDK, and `Glob` can decide happens before a single subagent token is spent:**

1. **Pre-flight** (is this even .NET?) — pure `Glob`. A non-.NET repo costs ~3K and never reaches the model pass.
2. **Phase 1** — the compiler/analyzers (`dotnet build`/`format`/`list package`) run off-context; the model only reads their summary.
3. **Phase 1.5 — candidate gathering** — a deterministic `Grep` pass collects the `file:line` sites for every check's seed pattern. This map **gates** Phase 2: a check with zero candidates costs zero tokens, and a whole group with zero candidates is **not dispatched at all**.
4. **Phase 2** — subagents *only judge the candidate list they're handed*. They read ±10 lines around each candidate and apply the calibration rules; they never scan the tree for discovery.

The result: **cost scales with the number of *suspected* sites, not with codebase size.** A clean, reviewed repo where the pre-pass finds few candidates costs a fraction of the headline estimate. This mirrors `mikko-skills-quality` and `mikko-skills-freshness` — a cheap deterministic pre-pass gates the expensive model pass.

## The checklist — five scopes, paired examples

Each check has a `Pattern`, a `Why`, a `Smell example`, a `Legitimate example` (the same shape when it's *fine*), and a `Severity default`. The auditor can upgrade or downgrade per finding when context warrants. **If a finding can't meet the smell+counter-example bar, it doesn't appear in the report.** The five scope groups (A–E) double as the five parallel-subagent bundles in Phase 2.

The outer fence below is 4 backticks so the inner code blocks render on GitHub.

````markdown
### Group A — DI & composition (ASP.NET Core)

#### A1. captive-dependency
- **Pattern.** A singleton (or longer-lived) service whose constructor captures a scoped or transient dependency — most often a `DbContext`. The container injects one instance and the singleton pins it forever, across every request and thread.
- **Why.** The captured scoped service outlives its scope. For `DbContext`: one shared instance, no per-request isolation, change-tracker bloat, and concurrent use across requests (it isn't thread-safe). This is the single most common serious DI bug in ASP.NET Core.
- **Smell.**
  ```csharp
  services.AddSingleton<FeedCache>();
  // ...
  public FeedCache(ApplicationDbContext db) => _db = db;   // ⚠️ scoped DbContext captured by a singleton
  ```
- **Legitimate.**
  ```csharp
  public FeedCache(IServiceScopeFactory scopes) => _scopes = scopes;
  // per use:
  using var scope = _scopes.CreateScope();
  var db = scope.ServiceProvider.GetRequiredService<ApplicationDbContext>();  // ✓ fresh scoped context per op
  ```
- **Severity default.** high (critical if the captured service is a `DbContext` used on concurrent requests).

#### A2. manual-httpclient-instantiation
- **Pattern.** `new HttpClient()` constructed per call (or per request) instead of going through `IHttpClientFactory` / a typed client.
- **Why.** Each `HttpClient` holds a socket handler; churning them exhausts sockets (TIME_WAIT) and caches DNS forever. The factory pools handlers and recycles them.
- **Smell.**
  ```csharp
  public async Task<string> Fetch(string url)
  {
      using var http = new HttpClient();             // ⚠️ new per call — socket exhaustion + stale DNS
      return await http.GetStringAsync(url);
  }
  ```
- **Legitimate.**
  ```csharp
  services.AddHttpClient<OpenLibraryClient>();        // ✓ typed client; factory owns the handler lifetime
  public OpenLibraryClient(HttpClient http) => _http = http;
  ```
  Also legitimate: a single `static readonly HttpClient` reused for the whole app lifetime, or `new HttpClient(handler)` inside a test.
- **Severity default.** high.

#### A3. service-lifetime-mismatch
- **Pattern.** A stateful or non-thread-safe service registered with the wrong lifetime — `DbContext` as singleton/transient instead of scoped; a service holding per-request state as singleton; a heavy stateless helper as transient (churn).
- **Why.** Lifetime is correctness, not just performance. A singleton holding mutable per-user state leaks data across users.
- **Smell.** `services.AddSingleton<ApplicationDbContext>();` — or a service field that accumulates per-request data registered `AddSingleton`.
- **Legitimate.** `services.AddDbContext<ApplicationDbContext>()` (scoped by default); stateless pure helpers as singleton; the HTML sanitizer / `IMemoryCache` as singleton.
- **Severity default.** high for `DbContext`; medium otherwise.

#### A4. ioptions-binding-bypass
- **Pattern.** Injecting `IConfiguration` and reading `config["Section:Key"]` by string in business code, instead of binding to a typed options class; or using `IOptions<T>` where reloadable config is genuinely needed (`IOptionsSnapshot`/`IOptionsMonitor`).
- **Why.** String keys lose validation, defaults, and refactor-safety. `IOptions<T>` is a startup snapshot — fine for static config, wrong when the value must reload.
- **Smell.** `var key = _config["GoogleBooks:ApiKey"];` scattered through a service.
- **Legitimate.** `IOptions<GoogleBooksOptions>` bound once at startup and injected (correct for config fixed at boot — the common case). `IOptionsMonitor<T>` only where reload is required.
- **Severity default.** low (medium if the bypass also skips a validation the options class would enforce).

### Group B — EF Core & data access

#### B1. missing-asnotracking
- **Pattern.** A read-only query — its results are projected/returned to a view and never mutated + saved — that does not call `AsNoTracking()`.
- **Why.** The change tracker snapshots every returned entity; on read-heavy paths that's wasted memory and CPU, and it can mask accidental writes.
- **Smell.**
  ```csharp
  var books = await _db.Books.Where(b => b.UserId == userId).ToListAsync(ct);  // ⚠️ tracked, only rendered
  return books.Select(ToDto).ToList();
  ```
- **Legitimate.**
  ```csharp
  var books = await _db.Books.AsNoTracking().Where(b => b.UserId == userId).ToListAsync(ct);  // ✓
  ```
  Also legitimate: the query loads entities that are then modified and `SaveChangesAsync`d — tracking is required, so no flag. **And a `.Select(x => new …Dto{…})` projection** returns non-entity types EF Core never tracks, so `AsNoTracking()` is redundant — never flag a projected query (this is the most common B1 false positive).
- **Severity default.** low (medium on a hot path returning many rows).

#### B2. client-side-evaluation
- **Pattern.** Materialising early (`.ToList()` / `.AsEnumerable()`) and then filtering/paging/ordering in memory; or calling a method EF can't translate inside the `IQueryable`, forcing a full-table pull.
- **Why.** Moves work the database should do into the app — full-table reads, N+1, memory blowups — often silently.
- **Smell.**
  ```csharp
  var all = await _db.ReadEntries.ToListAsync(ct);                 // ⚠️ pulls every row...
  var page = all.Where(e => e.UserId == userId).Take(20).ToList(); // ...then filters in memory
  ```
- **Legitimate.**
  ```csharp
  var page = await _db.ReadEntries.Where(e => e.UserId == userId).Take(20).ToListAsync(ct);  // ✓ DB does it
  ```
  Also legitimate: a deliberate in-memory projection after a *bounded* fetch, with a comment naming why.
- **Severity default.** high.

#### B3. missing-cancellationtoken
- **Pattern.** Async EF / `HttpClient` / downstream-service calls on a request path that don't accept and forward the request's `CancellationToken`.
- **Why.** Abandoned requests (client disconnects, timeouts) keep running queries and holding connections. Cancellation is how ASP.NET Core sheds load.
- **Smell.**
  ```csharp
  public async Task<List<BookDto>> GetLibrary(string userId)
  {
      return await _db.Books.Where(b => b.UserId == userId).ToListAsync();  // ⚠️ no CancellationToken
  }
  ```
- **Legitimate.**
  ```csharp
  public async Task<List<BookDto>> GetLibrary(string userId, CancellationToken ct)
      => await _db.Books.Where(b => b.UserId == userId).ToListAsync(ct);     // ✓ threaded through
  ```
  Also legitimate: a shared cache-populate that intentionally uses `CancellationToken.None` because the entry outlives the triggering request — **with a comment saying so**. (Immunised by the documented-intent rule.)
- **Severity default.** medium.

#### B4. dbcontext-concurrent-use
- **Pattern.** The same `DbContext` instance used by two operations awaited concurrently (`Task.WhenAll` over queries on one context; parallel `foreach` issuing queries).
- **Why.** `DbContext` is explicitly **not thread-safe**. Concurrent use throws `InvalidOperationException` ("A second operation started on this context…") or corrupts the change tracker — intermittently, under load.
- **Smell.**
  ```csharp
  var booksTask   = _db.Books.CountAsync(ct);
  var entriesTask = _db.ReadEntries.CountAsync(ct);
  await Task.WhenAll(booksTask, entriesTask);   // ⚠️ two ops on ONE context concurrently
  ```
- **Legitimate.** Await sequentially on the shared context, or give each parallel branch its own context via `IDbContextFactory<T>` / a fresh scope.
- **Severity default.** high.

#### B5. unbounded-query
- **Pattern.** `.ToListAsync()` over a table that grows with usage (per-user logs, a shared catalogue, an audit feed) with no `.Take()` / paging.
- **Why.** Works in dev with 10 rows, OOMs (or times out) in production with 100K. The absence of a bound is the bug.
- **Smell.** `var feed = await _db.ReadEntries.OrderByDescending(e => e.CreatedAt).ToListAsync(ct);` for a public feed.
- **Legitimate.** A genuinely bounded set (a lookup/enum table; a query already constrained to one owner with a natural small cardinality), or an explicit `.Take(N)`.
- **Severity default.** medium (high on a public / unauthenticated path).

### Group C — async/await & concurrency

#### C1. sync-over-async
- **Pattern.** `.Result`, `.Wait()`, or `.GetAwaiter().GetResult()` on a `Task` from a request/UI path.
- **Why.** Blocks a thread-pool thread waiting on async work; under load this starves the pool, and with a captured synchronization context it deadlocks outright.
- **Smell.**
  ```csharp
  var results = SearchAsync(query, ct).Result;   // ⚠️ blocks the thread; deadlock-prone
  ```
- **Legitimate.**
  ```csharp
  var results = await SearchAsync(query, ct);     // ✓
  ```
  Also legitimate: top-level composition in `Program.cs`/`Main` before the host runs, or a documented context with no sync-context where blocking is intentional.
- **Severity default.** high.

#### C2. async-void
- **Pattern.** `async void` on anything that isn't an event handler.
- **Why.** Exceptions thrown from `async void` can't be caught by the caller — they tear down the process. The method also can't be awaited, so callers race ahead of its completion.
- **Smell.**
  ```csharp
  public async void LogBook(LogBookRequest req) => await _service.LogAsync(req);  // ⚠️ exceptions escape; not awaitable
  ```
- **Legitimate.**
  ```csharp
  public async Task LogBook(LogBookRequest req) => await _service.LogAsync(req);  // ✓
  ```
  `async void` is acceptable *only* for a genuine event-handler signature (`void Handler(object? s, EventArgs e)`).
- **Severity default.** high.

#### C3. fire-and-forget-unobserved
- **Pattern.** Starting a task and discarding it (`_ = DoAsync();` or a bare `DoAsync();`) with no continuation observing exceptions or logging.
- **Why.** A faulted unobserved task fails silently; the work may never complete, and you find out via missing data, not an error.
- **Smell.** `_ = _emailSender.SendAsync(msg);` with nothing handling a throw.
- **Legitimate.** Explicitly backgrounded work that handles its own exceptions (try/catch + log) and is documented as best-effort, or work handed to a proper `BackgroundService` / `Channel`.
- **Severity default.** medium.

### Group D — web surface (Razor Pages / MVC) — skipped if no `.cshtml`/`.razor`

#### D1. html-raw-untrusted
- **Pattern.** `@Html.Raw(...)` / `MarkupString` / `HtmlString` on a value that isn't a compile-time constant and didn't pass through a sanitizer.
- **Why.** Razor auto-encodes by default; `@Html.Raw` opts out. On third-party HTML (book descriptions, user bios) that's stored/reflected XSS.
- **Smell.**
  ```cshtml
  @Html.Raw(Model.Description)            @* ⚠️ third-party HTML rendered raw *@
  ```
- **Legitimate.**
  ```cshtml
  @Html.Raw(Model.SanitizedDescription)  @* ✓ ran through an HtmlSanitizer; target attr stripped *@
  ```
  Also legitimate: `@Html.Raw` on a trusted, code-defined constant (an SVG icon string the app ships).
- **Severity default.** critical when the input crosses a trust boundary; otherwise medium.

#### D2. overposting-via-bindproperty
- **Pattern.** `[BindProperty]` (or an action parameter) binding directly to an EF entity or a model that exposes fields the form shouldn't set (`UserId`, `IsAdmin`, `Rating` bounds, `Id`).
- **Why.** Mass assignment: a crafted POST sets fields the UI never showed, bypassing ownership/authorization.
- **Smell.**
  ```csharp
  [BindProperty] public ReadEntry Entry { get; set; }   // ⚠️ binds UserId, Id, every column
  ```
- **Legitimate.**
  ```csharp
  [BindProperty] public UpdateReadEntryRequest Input { get; set; }  // ✓ DTO with only the editable fields
  ```
  Also legitimate: explicit `[Bind(nameof(...))]` allow-list, or `await TryUpdateModelAsync(entity, "", e => e.Title, e => e.Rating)`.
- **Severity default.** high.

#### D3. mutation-on-get
- **Pattern.** A handler that changes state on `OnGet`/an HTTP GET action — writes the DB, signs the user out, deletes.
- **Why.** GETs are cacheable, prefetchable, and CSRF-unprotected. State change on GET is the classic CSRF / accidental-mutation footgun.
- **Smell.**
  ```csharp
  public async Task<IActionResult> OnGet() { await _signInManager.SignOutAsync(); return Redirect("/"); }  // ⚠️
  ```
- **Legitimate.** `OnGet` reads only; the sign-out / write lives in `OnPost` with the antiforgery token. (A GET to a sign-out route must NOT sign out.)
- **Severity default.** high.

#### D4. open-redirect
- **Pattern.** `Redirect(returnUrl)` / `Redirect(userInput)` where the URL is request-supplied, instead of `LocalRedirect` or an `Url.IsLocalUrl(returnUrl)` guard.
- **Why.** An attacker crafts `?returnUrl=https://evil.example` and the post-login redirect sends the authenticated user off-site (phishing, token leak).
- **Smell.**
  ```csharp
  return Redirect(returnUrl);        // ⚠️ returnUrl is from the query string
  ```
- **Legitimate.**
  ```csharp
  return LocalRedirect(returnUrl);   // ✓ throws if the URL isn't local
  ```
  Also legitimate: redirect to a hard-coded/known-safe route.
- **Severity default.** high.

### Group E — error handling & resource lifecycle

#### E1. swallowed-exception
- **Pattern.** `catch { }`, `catch (Exception) { }`, or `catch (...) { return null/default/empty; }` with no logging, no rethrow, and no comment naming why.
- **Why.** The failure vanishes; downstream debugging becomes archaeology. (The .NET form of the universal swallowed-errors smell.)
- **Smell.**
  ```csharp
  try { await _client.SearchAsync(q, ct); }
  catch (Exception) { }                       // ⚠️ what failed? what state are we in now?
  ```
- **Legitimate.**
  ```csharp
  catch (DbUpdateException)
  {
      // Unique-index race: another request created the same Book first. Detach and re-fetch the winner.
      entry.State = EntityState.Detached;
      return await _db.Books.SingleAsync(b => b.OpenLibraryId == id, ct);
  }
  ```
  Or a provider-degradation catch that logs AND returns `[]` AND comments the intent (the `Promise.allSettled` analogue). Has a log call or a recovery *and* a reason.
- **Severity default.** high (critical when the swallowed block wrapped a write or a state mutation).

#### E2. catch-all-swallows-cancellation
- **Pattern.** `catch (Exception)` that also catches `OperationCanceledException` / `TaskCanceledException` and turns it into a "normal" result (empty list, false, default) without re-throwing.
- **Why.** Cancellation is not a failure to absorb — swallowing it reports a cancelled request as a successful empty result, masks shutdown, and can hide real timeouts.
- **Smell.**
  ```csharp
  try { return await _client.GetAsync(ct); }
  catch (Exception) { return Array.Empty<BookDto>(); }   // ⚠️ also eats OperationCanceledException
  ```
- **Legitimate.**
  ```csharp
  catch (Exception ex) when (ex is not OperationCanceledException) { return Array.Empty<BookDto>(); }  // ✓ lets cancellation propagate
  ```
- **Severity default.** medium.

#### E3. idisposable-not-disposed
- **Pattern.** An `IDisposable` / `IAsyncDisposable` created and owned by the code (a `SqlConnection`, `StreamReader`, `CancellationTokenSource`, `new HttpClient(handler)`) without a `using` / `await using` / explicit `Dispose`, and not handed to the DI container to own.
- **Why.** Leaks unmanaged handles and connections; under load, pool/handle exhaustion.
- **Smell.**
  ```csharp
  var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
  var resp = await _http.GetAsync(url, cts.Token);   // ⚠️ cts never disposed
  ```
- **Legitimate.** `using var cts = ...;`. DI-registered disposables (the container disposes them at scope end). And the inverse non-bug: an `HttpClient` obtained from `IHttpClientFactory` must **not** be disposed — flagging that would be wrong.
- **Severity default.** medium.
````

## Calibration rules

These rules are blocking — apply them before recording any finding.

- **Trust boundaries are immune.** Defensive handling of user input, config-loaded values, external HTTP responses, and DB exceptions at the boundary is legitimate, not a smell.
- **Documented intent immunises a line.** A comment naming the choice (`// CancellationToken.None: entry outlives this request`, `// Detach + re-fetch on unique-index race`, `// Defensive: external HTML`) means the author considered it. An `// audit:dotnet:ignore <check> — <reason>` comment is the explicit opt-out.
- **`CLAUDE.md` / documented invariants win.** If the repo documents a behaviour (e.g. "the cache-populate uses `CancellationToken.None`", "ownership returns 404 not 403", "OpenLibraryClient throws, GoogleBooksClient returns []"), that is the spec — do not flag the code for honouring it.
- **DI-owned lifetimes are immune.** Services and disposables registered in the container are disposed by the container; `HttpClient` from the factory must not be disposed. Don't flag either.
- **Generated code is out of scope.** `obj/`, `bin/`, `*.g.cs`, `*.Designer.cs`, EF migrations' `Designer`/`ModelSnapshot` files — never audited.
- **Tests get a partial pass.** Test projects deliberately use `new HttpClient(stubHandler)`, block on tasks in `[Fact]` bodies, and over-bind fixtures. Only flag tests for `swallowed-exception` and genuinely leaked process-wide resources.
- **One occurrence is data; many is a fingerprint.** A single low-severity hit is informational; density (the same check ≥5 times in a file, ≥15 in a project) upgrades severity by one level and is worth a note in the report.

## Procedure

### Phase 0 — pre-flight

See the **Pre-flight check** section. Bail if not .NET (unless `--force`). Honour `--source <path>` to scope the whole run to a subtree.

### Phase 1 — static analysis (best effort)

The .NET toolchain *is* a static analyser. Run these from the repo root; for each: try it, capture stdout+stderr+exit code; if the tool/SDK is unavailable, skip cleanly and record it under "Skipped" with a one-line reason. **Never fabricate output for a skipped tool. Never run a tool that mutates** (`dotnet format` *without* `--verify-no-changes`, `dotnet ef database update`, etc.).

1. `dotnet build -c Release` — surfaces analyzer diagnostics and (if the project treats them as errors) nullable warnings. Report the warning/error count and the top 5 by category; do not re-list them as findings (they're the build's job).
2. `dotnet format --verify-no-changes` — whitespace/style drift (read-only; reports, doesn't write).
3. `dotnet list package --vulnerable --include-transitive` and `dotnet list package --outdated` — dependency risk.
4. `dotnet test` is **optional** and off by default (can be slow / require a DB); run only if the user asks.

Summarise per tool: **Ran** → pass / N findings (top categories); **Skipped** → reason. Do not fix anything here.

### Phase 1.5 — candidate gathering (deterministic, no AI tokens)

This is the load-bearing token-economy step: **find candidate sites with `Grep` before any subagent runs.** No model judges anything yet — ripgrep collects `file:line` hits for every check's seed pattern, and that candidate map *gates* Phase 2.

1. Build the file set for the scope (`--source` or repo root), excluding `obj/`, `bin/`, `*.g.cs`, `*.Designer.cs`, `Migrations/*ModelSnapshot.cs`.
2. Run each seed pattern below with `Grep` (it's ripgrep under the hood; use `multiline: true` where noted). Collect `{check, file, line, matched-text}`.
3. Build the candidate map grouped A–E and **record per-check candidate counts** — they seed the report's "Per-check tally" and drive the dispatch gate.
4. **Gate dispatch:** for each group, if total candidates == 0, **do not dispatch that subagent** — mark the group "0 candidates — not dispatched". Otherwise dispatch the subagent with *only its group's candidate list* (file:line + matched line).

Seed patterns (ripgrep syntax; starting nets, not proofs — the subagent confirms each against the smell/legitimate examples):

| Check | Seed pattern (`rg`) | Judge step narrows on |
| --- | --- | --- |
| A1 captive-dependency | `AddSingleton<` | …the registered type's ctor capturing a scoped service |
| A2 manual-httpclient-instantiation | `new HttpClient\(` | …not a factory/typed client, not a test |
| A3 service-lifetime-mismatch | `Add(Singleton\|Scoped\|Transient)<` | …stateful/non-thread-safe type, wrong lifetime |
| A4 ioptions-binding-bypass | `_config\[\|IConfiguration` | …string-key reads that should be bound options |
| B1 missing-asnotracking | `\.(ToListAsync\|FirstOrDefaultAsync\|SingleAsync\|ToArrayAsync)\(` | …read-only path, no `AsNoTracking()`, **and not a `.Select(…)` projection** (EF doesn't track non-entity projections) |
| B2 client-side-evaluation | `\.ToList\(\)\|\.AsEnumerable\(\)` | …followed by LINQ filtering/paging |
| B3 missing-cancellationtoken | `Async\(` *(multiline)* | …`ct` in scope but not forwarded |
| B4 dbcontext-concurrent-use | `Task\.WhenAll\|Parallel\.For` | …same `DbContext` in the awaited tasks (not two HTTP clients) |
| B5 unbounded-query | `\.ToListAsync\(` | …growable table, no `.Take(` |
| C1 sync-over-async | `\.Result\b\|\.Wait\(\)\|\.GetAwaiter\(\)\.GetResult\(\)` | high-precision; judge confirms request path |
| C2 async-void | `async void ` | …not an event-handler signature |
| C3 fire-and-forget-unobserved | `_ = \w+.*Async\(` *(multiline)* | …unawaited, no exception handling |
| D1 html-raw-untrusted | `Html\.Raw\(\|MarkupString\|new HtmlString` | …value not sanitised / not a constant |
| D2 overposting-via-bindproperty | `\[BindProperty\]` | …bound to an EF entity, not a DTO |
| D3 mutation-on-get | `OnGet` *(multiline +body)* | …writes / `SignOut` / `Remove` in the body |
| D4 open-redirect | `Redirect\(` | …user-supplied URL, not `LocalRedirect` |
| E1 swallowed-exception | `catch\s*(\([^)]*\))?\s*\{` *(multiline)* | …empty / no-log / returns default |
| E2 catch-all-swallows-cancellation | `catch \(Exception` *(multiline)* | …no `when (… is not OperationCanceledException)` |
| E3 idisposable-not-disposed | `new \w+(Connection\|Reader\|Writer\|Stream\|CancellationTokenSource)\(` | …owned, no `using`, not DI-owned |

If the `Grep` tool is somehow unavailable, the subagents fall back to scanning directly — and the report notes the pre-pass was skipped so the reader knows tokens weren't bounded.

### Phase 2 — parallel subagents (up to five, candidate-gated)

Dispatch **only the groups Phase 1.5 found candidates for** (one message, parallel `Agent` calls, `subagent_type: "Explore"` — the audit is read-only). Hand each subagent **its group's candidate list** (file:line + matched line); it judges those candidates — reads ±10 lines of context around each, applies the Calibration rules, and emits a finding only when the shape matches the smell and not the legitimate counter-example. **Subagents do not scan the tree for discovery** — discovery already happened deterministically in Phase 1.5. Scopes A–E are non-overlapping; if an issue straddles two, the more specific group claims it. Group D is skipped when there's no web surface *or* no D-candidates.

**Large repos (> ~300 source files):** if a group's candidate list is itself huge, split it across two subagents by file glob and note the split on the Coverage line.

Each subagent returns findings in this exact line format so Phase 3 aggregates without transformation:

```
- [path/File.cs:NN](path/File.cs#LNN) [severity] — <check-name>: one-line description
```

severity ∈ {critical, high, medium, low}.

#### Subagent prompt templates

Append to **every** subagent prompt:

> You are handed a **candidate list** — `file:line` sites a deterministic ripgrep pre-pass already found for your group's checks. **Judge each candidate; do not scan the tree for new ones.** For each, read ±10 lines of context and decide whether it matches the smell shape or the legitimate counter-example. A candidate's context may point you a few lines away (a constructor, a registration, a usage) — follow that, but don't go prospecting beyond it.
>
> Output format — one line per finding, exact template:
> `- [path/File.cs:NN](path/File.cs#LNN) [severity] — <check-name>: one-line description`
> severity ∈ {critical, high, medium, low}. Apply the Calibration rules from the skill: trust boundaries, `// audit:dotnet:ignore` comments, documented `CLAUDE.md` invariants, DI-owned lifetimes, and generated/`obj`/`bin`/`*.g.cs`/`*.Designer.cs` files are all immune. Emit nothing for a candidate that matches the legitimate counter-example. Do not fabricate — every finding cites a real file:line you can open. Cap your reply at ~400 words.

1. **DI & composition** — your candidates are `AddSingleton`/`AddScoped`/`AddTransient`/`new HttpClient(`/`_config[` sites. Confirm checks **A1–A4** by reading the registered type's constructor for each registration candidate: captive dependencies (singleton capturing scoped, esp. `DbContext`), `new HttpClient()` outside the factory, lifetime mismatches, `IConfiguration` string-key reads that should be bound options.
2. **EF Core & data access** — your candidates are query-materialisation and async-call sites. Confirm **B1–B5**: missing `AsNoTracking()` on read-only paths, early `ToList()`/`AsEnumerable()` then in-memory filtering, async EF calls missing a `CancellationToken`, one `DbContext` used across concurrent awaits, unbounded `ToListAsync()` on growable tables.
3. **Async & concurrency** — your candidates are `.Result`/`.Wait()`/`async void`/`_ = …Async(` sites. Confirm **C1–C3**: sync-over-async on request paths, `async void` on non-event-handlers, unobserved fire-and-forget tasks.
4. **Web surface** — your candidates are `Html.Raw`/`[BindProperty]`/`OnGet`/`Redirect(` sites in `*.cshtml`/`*.razor`/`*.cshtml.cs`. Confirm **D1–D4**: raw output of unsanitised values, binding to EF entities (overposting), state mutation on GET, open redirects. (This agent isn't dispatched if there's no web surface or no candidates.)
5. **Errors & resources** — your candidates are `catch` blocks and `new …(Connection|Stream|…)` sites. Confirm **E1–E3**: swallowed exceptions (no log/rethrow/comment), `catch (Exception)` that also eats `OperationCanceledException`, owned `IDisposable` not disposed (excluding factory `HttpClient` and DI-owned services).

### Phase 3 — aggregated report

Write `docs/audits/dotnet-<YYYY-MM-DD>.md` (create `docs/audits/` if absent). If a file for the same date exists, suffix `-v2`, `-v3`, … — **never overwrite**. Recount the severity tally so the summary matches the body exactly.

## Output schema

The outer fence is 4 backticks so the inner blocks render.

````markdown
# .NET audit — {YYYY-MM-DD}

## Summary
- Commit audited: `<git rev-parse HEAD>` on branch `<git branch --show-current>`
- Scope: {project root or --source path}
- Pre-flight: {one-liner}
- Coverage: Phase 1 {ran|skipped: reason}; Phase 2 {N of 5} subagents dispatched — groups with 0 candidates skipped (A DI · B EF Core · C async · D web · E errors/resources)
- Total findings: N (critical: N · high: N · medium: N · low: N)

## Per-check tally

| Check | Findings |
| --- | ---: |
| A1 captive-dependency | 0 |
| B3 missing-cancellationtoken | 4 |
| … | … |
| **Total** | **N** |

## Static analysis
<Phase 1 per-tool output, or which tools were unavailable and why>

## Findings by area

### A — DI & composition
- [src/ReadLog.Web/Program.cs#L48](src/ReadLog.Web/Program.cs#L48) [high] — A1 captive-dependency: singleton FeedCache captures scoped ApplicationDbContext.

### B — EF Core & data access
### C — async/await & concurrency
### D — web surface
### E — error handling & resources

## Recommended next steps
<grouped by severity, critical first. Suggest fix branches — area-named (`fix/dotnet-di`, `fix/dotnet-efcore`) when an area has enough findings, or numbered batches otherwise. Note rough commit count per branch. Close with: "Work in parallel across branches; the five scopes are non-overlapping by construction.">

## What's verifiable vs editorial
<the table below>
````

## Output discipline

- **Never fabricate.** Every finding cites a real `file:line` in the working tree. If in doubt, leave it out.
- **Don't suggest fixes inline.** The report is a defect list, not a patch list — fixes land on follow-up branches so each is reviewed independently.
- **Preserve the project's own naming.** Identifiers stay verbatim.
- **Severity tally must match the body.** If the summary says "critical: 2", the body has exactly two `critical` findings. Recount before writing the summary.
- **Read-only.** No `--fix` flag exists; the human judgement that separates signal from noise *is* the product.

## Flags

- `--source <path>` — audit only the given directory (default: repo root). Useful for solutions with many projects: `--source src/ReadLog.Web`. **Documented support** — `mikko-audit-suite` forwards `--source` to this skill.
- `--force` — bypass the pre-flight bail; records the override in the report header. Use only for a known-wrong negative (source tree generated into an unusual layout, single-file top-level program, etc.).
- `--scope <glob>` — passed through to the Phase 2 subagents as a context-narrowing hint on large repos.

## Token expectations

Author estimate (not measured — run `/mikko-skill-usage` for receipts). For a small-to-medium .NET repo (~40–200 hand-written `.cs` files):

- Pre-flight: ~3K (Globs + a couple of Reads).
- Phase 1 (dotnet build/format/list dispatch + capture): ~5K main; the tool runs are off-context.
- **Phase 1.5 (ripgrep candidate gathering): ~3–6K main, zero subagent tokens.** This is the step that bounds everything after it.
- Phase 2 (parallel Explore subagents — *only for groups with candidates*, judging a candidate list rather than scanning): ~15–60K per **dispatched** group; a zero-candidate group costs **0**.
- Phase 3 (aggregation + report write): ~10–15K output.

**Total scales with suspected sites, not codebase size.** A messy repo with hits in every group ≈ ~25K main + ~250K dispatched. A clean, reviewed repo where the pre-pass clears whole groups can land **under ~80K**. A single-project `--source` or branch-diff run, lower still. This is the deliberate consequence of the deterministic-before-dispatch design (see **Token economy** above).

Cadence: per substantial backend PR, and 1–2× per month on an actively-iterating .NET service. ~12–24 uses/year per repo.

## Failure modes

- **Pre-flight bails on a real .NET codebase.** Single-file top-level programs, or a solution whose `.csproj` lives outside the audited subtree, can trip the matrix. Override with `--force` (recorded in the header) or point `--source` at the project.
- **No SDK in the environment.** Phase 1 skips cleanly (recorded under "Skipped"); Phase 2 still runs — the subagents read source, they don't need `dotnet`.
- **F# / VB.NET.** The checks are C#-shaped. F#/VB projects pass the project-file pre-flight but most checks won't match their idioms. Treat findings as best-effort and lean on `mikko-audit` for those.
- **Blazor.** `*.razor` is detected as a web surface, but D1–D4 are Razor-Pages/MVC-shaped; Blazor's component model has its own hazards (render-tree, `StateHasChanged`, `IDisposable` components) not covered in v1 — closer to a future `blazor-anti-patterns-audit`.
- **Minimal APIs.** Endpoint-defined-inline apps have no page/controller classes; group D's overposting/GET-mutation checks lean on the endpoint lambdas instead and may under-detect. The DI/EF/async/error groups are unaffected.
- **Heuristic matching.** Captive-dependency and overposting in particular need the auditor to connect a registration to a constructor, or a binding to a type — expect occasional false positives; the counter-example column tells the reader when a hit is fine.

## Limitations

First iteration. Deliberately out of v1, each worth a future check:

- **EF migration correctness** (a migration that drops a column with data, a non-idempotent seed) — needs migration-diff analysis, not source grep.
- **Connection-resiliency / retry config** (`EnableRetryOnFailure`, transient-fault handling) — judgement-heavy.
- **Output-caching / response-caching correctness** and `IMemoryCache` eviction races — overlaps `mikko-audit`'s concurrency scope.
- **Authorization-policy gaps** (missing `[Authorize]`, resource-based auth holes) — that's `mikko-security-audit`'s remit; this skill flags only the mechanical web shapes (D1–D4).
- **Middleware-ordering bugs** (`UseForwardedHeaders` after the auth middleware, exception handler in the wrong place) — planned for the DI/composition group in a later iteration.

## What's verifiable vs editorial

| Claim | Source of truth | Verifiable? |
| --- | --- | --- |
| Is this a .NET codebase? | `.csproj`/`.sln` + `.cs` files | ✅ Yes (pre-flight) |
| Does pattern X appear at file:line Y? | The source file | ✅ Yes |
| Is pattern X a bug *here*? | Human judgement | 🟡 Heuristic (the counter-example tells you when it isn't) |
| Severity of a finding | The default + auditor adjustment | 🟡 Heuristic |
| Which fix to apply | Out of scope — the report is a defect list | — |

Every finding cites file:line and a check name; a human opens the file and judges it against the paired smell/legitimate examples. The skill never says "this is a bug, fix it" — it says "this matches a documented .NET smell shape; you decide."

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill — they assert the skill's load-bearing pieces still ship / stay documented. See that skill for the check vocabulary.

```toml
[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "captive-dependency"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "pre-flight"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "parallel subagents"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "candidate gathering"
```
