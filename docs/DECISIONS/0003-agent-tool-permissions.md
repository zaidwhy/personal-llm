# ADR 0003: Three-tier tool permission model, allow-listed per agent run (not per tool)

**Status:** Accepted

**Context:** v0.2 gives the agent the ability to act (read memory, write memory, fetch the web), which is qualitatively riskier than v0.1's read-only RAG. The TDD's Security & Privacy section requires every tool action to be permission-gated and audited, not just logged after the fact.

**Decision:** Every `Tool` declares one `permission` tier: `read_only` (e.g. `memory_search`, `read_file`), `read_write` (e.g. `remember`), or `network` (e.g. `web_fetch`). An `Agent` run is constructed with an explicit `allowed_permissions` set - default `{read_only}` only. The `ToolRegistry.invoke()` checks the tool's tier against that set before validating args or executing anything; a denied call returns a normal `ToolResult(ok=False, ...)` that the agent sees as an observation and can reason about, not an exception that crashes the loop. CLI/API callers opt in per-run via `--allow-network`/`--allow-write` flags (or request fields), never a global setting - so a script that forgot to ask for `network` fails safe instead of silently reaching the internet.

`read_file` is additionally sandboxed to a dedicated `data/workspace/` directory (path-traversal checked via `Path.resolve()` containment) regardless of permission tier, and `web_fetch` resolves the hostname and rejects private/loopback/link-local/reserved targets before connecting (SSRF guard), with redirects refused rather than auto-followed.

**Consequences:** Adding a new tool is a new `Tool` subclass with a declared tier - no changes to the gating logic. The three tiers deliberately do not distinguish between individual tools within a tier (e.g. all `network` tools share one flag) - that's a reasonable v0.2 granularity for a personal single-user agent; per-tool allow-lists are deferred until there's a second `network` tool where it would actually matter. The SSRF guard resolves DNS once before the request and does not defend against DNS-rebinding between check and connect - acceptable for a local personal tool, not for a multi-tenant service.
