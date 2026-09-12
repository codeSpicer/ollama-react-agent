# ollama-react-agent — ReAct Tool-Using Agent (with MCP)

> Standalone repo for this project. Curriculum source: `ai-engineer-roadmap`
> Phase 2 · Skill Agents · Project A.

**Phase:** 2 — Building AI Apps · **Skill:** Agents · **Difficulty:** Intermediate

A single agent that reasons, selects tools, and acts in a loop until it produces a final answer.
Includes **two tool-integration paths**: plain in-process function-calling and a
**Model Context Protocol (MCP)** server. **Local-first: Ollama function-calling model, zero API keys.**
Build the loop **framework-free first** (raw `ollama.chat` + manual dispatch), then compare against
a framework — the hand-rolled version is where the learning lives.

An agent = LLM brain + tool hands + observation loop. The LLM never touches the world directly;
it emits structured tool requests, your runtime executes them, results come back as observations,
and the loop repeats until Final Answer or max-steps.

## Links to roadmap.sh/ai-engineer

- AI Agents (ReAct, tools / function calling)
- Model Context Protocol (MCP) — folded into this skill

## Concepts covered

The agent loop (reason → act → observe), tool schemas (JSON Schema as the model/runtime contract),
ReAct prompting (Thought/Action/Observation interleaving), native function-calling vs prompt-parsed
actions, error-as-observation handling, max-steps termination guards, reasoning-trace inspection,
MCP (server/client, discovery, transport decoupling), framework-free vs framework debugging tradeoffs.

## Prerequisites

- Foundations Project A (sampling params, system/user roles, JSON mode — all reused under the hood)
- Ollama with a function-calling-capable model (`qwen3.5:4b` — tier guide for 16GB Macs in root `MODELS.md`)
- `uv pip install ollama mcp` (+ `requests` for web-search/API tools)

## Learning objectives

- Implement the reason/act/observe loop by hand and read a full trace explaining each tool decision
- Define tools with clear JSON schemas, descriptions that drive selection, and validated args
- Make tool failures into observations the model can recover from (not crashes)
- Expose one tool as an MCP server and consume it through MCP — and articulate what MCP buys over in-process calls

## How it works (the loop)

```
user task
  │
  ▼
prompt = system (role + tool schemas + ReAct format) + history (thoughts, actions, observations)
  │  ollama.chat(model, messages, tools=[...])
  ▼
model output:  Thought: ...  →  Action: tool_name(args)   OR   Final Answer: ...
  │                                              │
  │ dispatch                                     └─ done → return answer + trace
  ▼
registry[tool_name](validated_args)  →  Observation: <result or ERROR: ...>
  │  append to history; steps += 1; if steps > MAX → force-terminate
  └─ loop (model sees the observation, reasons again)

Two wirings for the SAME tool:
  in-process:  registry["read_file"] = python function      (direct call)
  MCP:         registry["read_file"] = mcp_client.call(...) (via MCP server subprocess)
```

The trace (every Thought/Action/Observation with timestamps) is the primary artifact —
"you can read the trace and explain each tool decision" is the definition of done.

## Setup

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
ollama serve
ollama pull qwen3.5:4b

# Sanity: model must support tools — if it emits fake JSON instead of tool_calls, switch models
python -m react_agent run "what is 17 * 23?" --trace
python -m react_agent run "read NOTES.md and summarize it" --trace
python -m react_agent run "search the web for <topic> and save findings to out.md" --trace --mcp
```

| Flag | Where | Default | Meaning |
| ---- | ----- | ------- | ------- |
| `--trace` | run | off | print every Thought/Action/Observation |
| `--max-steps` | run | `10` | loop guard before forced termination |
| `--mcp` | run | off | route eligible tools through the MCP server instead of in-process |
| `--model` | run | `qwen3.5:4b` | must support native `tools=` calling |
| `--log` | run | `trace.jsonl` | append machine-readable trajectory per run |

## Project layout (files you will create)

```
react-tool-agent/
├── requirements.txt
├── react_agent/
│   ├── __main__.py        `python -m react_agent` entry
│   ├── cli.py             run subcommand, flags, pretty trace printing
│   ├── loop.py            THE agent loop (prompt build → chat → dispatch → observe)
│   ├── tools.py           tool implementations + JSON SCHEMAS + registry
│   ├── mcp_server.py      same tools exposed as an MCP server (stdio)
│   ├── mcp_client.py      client wrapper matching the in-process registry interface
│   └── trace.py           JSONL trajectory log (thoughts, calls, args, results, ms)
├── evals/
│   └── tasks.md           8–12 multi-step tasks with expected tool sequences
└── README.md              this file + your measured tables
```

Tool set to implement (each: name, description, JSON schema, handler, error paths):
`calculator` (safe eval, no `eval()` on raw input) · `read_file` / `write_file` (sandboxed to workdir) ·
`web_search` (DuckDuckGo API or requests scraper) · one small JSON API (weather/time/stocks — your pick).

---

## Build phases (do these in order — they ARE the curriculum)

### Phase 0 — Task set first (before any agent code)

- [ ] Write `evals/tasks.md` with 8–12 tasks across 4 buckets:
  - **single-tool** (2–3): "what is 17*23" → calculator only.
  - **multi-step** (3–4): "search X, save summary to file" → search → write.
  - **error-recovery** (2–3): task whose first attempt SHOULD fail (bad path, missing arg) → agent must retry corrected.
  - **no-tool** (1–2): "write a haiku" → must answer directly with zero tool calls (over-triggering is a bug).
- [ ] Verify: for each task you can state the EXPECTED tool sequence. If you can't, the task is vague — rewrite it.

### Phase 1 — Tools + schemas (no LLM yet)

- [ ] `tools.py`: implement the 4–5 tools as plain functions with JSON schemas
  (`name`, `description`, `parameters` with types/required). Descriptions must say WHEN to use the tool —
  the model selects tools by reading these, so "reads a file" < "reads a UTF-8 text file under workdir; use when the task references a local file."
- [ ] Unit-test each tool directly (bad args, missing file, network down) — every failure returns a STRING error,
  never raises out of the registry.
- [ ] Verify: call each tool from a REPL with good + bad inputs; all bad inputs produce clean error strings.

### Phase 2 — The loop, framework-free (the core)

- [ ] `loop.py`: system prompt (role + tool list + ReAct format + "Final Answer:" convention) →
  `ollama.chat(tools=...)` → if `tool_calls`, validate args against schema → dispatch → append observation → repeat.
- [ ] Native tool-calling first (`tools=` param). Log whether the model used native calls vs free-text —
  if it emits fake JSON instead of `tool_calls`, your model is too weak: switch models, don't regex-parse around it
  (record which model failed — that's a finding).
- [ ] `--max-steps 10` guard: on exceed, force-terminate with partial trace (never hang, never infinite-bill).
- [ ] Verify: single-tool + no-tool tasks pass with a trace you can narrate line by line.

### Phase 3 — Errors as observations + multi-step

- [ ] Every tool exception → `"ERROR: <what> — <how to fix>"` observation fed back to the model
  (e.g. `ERROR: file not found: x.md — available files: a.md, b.md`).
- [ ] Run the multi-step + error-recovery buckets; keep traces where the agent visibly corrects itself.
- [ ] Verify: at least one error-recovery task shows Thought ("that path failed, trying…") → corrected Action → success.
  A crash or give-up on first error is a Phase-3 failure.

### Phase 4 — MCP server + client (same tools, second wiring)

- [ ] `mcp_server.py`: expose `read_file` (pick one tool first) as an MCP server over stdio
  (tool definition + handler, per MCP SDK docs).
- [ ] `mcp_client.py`: wrapper exposing the IDENTICAL `(name, schema, handler)` interface as `tools.py`
  so `loop.py` can't tell which wiring it's calling.
- [ ] `--mcp` flag swaps the registry entry from in-process to MCP-backed; run the same task both ways.
- [ ] Verify: identical task succeeds via both wirings; `--trace` shows which wiring served each call.
  Record added latency of the MCP hop (expect small but nonzero — measure yours).

### Phase 5 — Trace report (the deliverable)

- [ ] Run the FULL task set twice (in-process, MCP); fill the table below.
- [ ] Save 2 annotated traces: one clean multi-step success, one error→recovery — with a sentence per step
  explaining WHY the model chose that action.
- [ ] Write 1-page verdict: where the agent wastes steps, which tool descriptions caused mis-selections
  (and your rewrites), MCP cost/benefit in your numbers.

---

## Core experiments (fill in YOUR numbers)

### 1. Task-set pass table ← the core objective

| Task bucket (tasks) | in-process pass/total | MCP pass/total | avg steps | notes (mis-selections, fixes) |
| ------------------- | --------------------- | -------------- | --------- | ----------------------------- |
| single-tool         |                       |                |           |                               |
| multi-step          |                       |                |           |                               |
| error-recovery      |                       |                |           |                               |
| no-tool (0 calls?)  |                       |                |           |                               |

**What to look for:** single-tool ≈100% both wirings; multi-step is where steps get wasted;
error-recovery is where error-as-observation earns its keep; no-tool catches over-triggering
(a model that calls search for a haiku has a prompting problem).

### 2. Description-driven selection

Deliberately weaken one tool description ("does file stuff") and re-run 3 tasks that need it —
record mis-selection rate. Restore the precise description, re-run. This is your concrete proof that
schemas/descriptions ARE the tool-selection mechanism, not decoration.

### 3. Break it deliberately

- `--max-steps 2` on a 4-step task — confirm forced termination with a readable partial trace, not a hang.
- Kill network mid `web_search` task — the error must appear as an Observation the model reasons about.
- Ask a task referencing a file outside the sandbox (`/etc/passwd`-style) — confirm refusal/containment.
- `--mcp` with the MCP server NOT running — confirm a clean actionable error, not a traceback.

### 4. Model swap

Run the same 3 tasks on two Ollama models (e.g. `qwen3.5:4b` vs a larger `qwen` 7–8b).
Record: native tool-call compliance (did it use `tool_calls` or fake JSON?), steps wasted, pass/fail.
Tool-use ability varies enormously by model — your table makes that concrete.

## Observations worth writing down as you go

1. **Description → selection causality**: the before/after from experiment 2, verbatim.
2. **Native vs fake tool calls**: which model did what — this determines your minimum viable model.
3. **Error-message design**: which ERROR strings rescued the run vs which confused the model further.
4. **MCP hop cost**: your measured ms + complexity delta — "USB-C for tools" has a price; state it.
5. **Over-triggering instances**: tasks where zero tools were correct but the model called one anyway.

## Definition of done

- The agent completes multi-step tasks end-to-end and at least one tool call goes through MCP.
- Every run has a trace you can narrate: each Thought → Action → Observation explained.
- Task table is filled for both wirings; error-recovery bucket shows at least one visible self-correction.
- You can explain ReAct, why schemas matter, what max-steps protects against, and MCP vs in-process tradeoffs.

## Reference material

- huijunwu/learn-claude-code (s01–s03): https://github.com/huijunwu/learn-claude-code
- LangChain DeepAgents Playbook (Level 2–3): https://github.com/sdivyanshu90/LangChain-DeepAgents-Playbook
- Model Context Protocol: https://modelcontextprotocol.io/ · MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Ollama function calling: https://ollama.com/blog/tool-support

## Next

Project B turns this single loop into a TEAM: supervisor + specialists + shared state + human gates (LangGraph).
Keep `tools.py` — the workers reuse these tools.
