# Interview Questions — ReAct Tool-Using Agent with MCP (with Answers)

These questions simulate a real technical interview for an AI engineering role. Each answer is
grounded in **this project's actual code and the numbers you measured** — task pass tables, traces,
model-swap results, MCP latency. Quote your task table; that separates "read about agents" from "built one."

---

## Part 1: Fundamentals — "What IS an agent?"

**Q1. What is the difference between a plain LLM call and an agent? Be precise.**

**Answer:** A plain LLM call is stateless text-in/text-out: `ollama.chat(messages)` returns tokens and
forgets everything. An agent (`loop.py`) wraps the LLM in a SENSE–DECIDE–ACT loop with persistent history:
prompt (role + tool schemas + accumulated thoughts/actions/observations) → model output → runtime executes
the requested tool → observation appended to history → repeat until Final Answer or `--max-steps`. The LLM
never touches the world — it only emits structured requests; your runtime is the hands. Three consequences:
the agent can use information that didn't exist at prompt time (search results), it can recover from its own
errors (observation says ERROR, next thought adapts), and it needs termination logic (a pure LLM call always
returns; a loop can spin forever). "Agents act; LLMs only answer" is the one-liner; the loop + registry +
history + guard in `loop.py` is the substance.

**Q2. Walk me through one multi-step task end to end, naming every file that touches it.**

**Answer:** Take "search the web for <topic>, save findings to out.md" with `--trace`: (1) `cli.py` parses
the task, loads the registry from `tools.py` (schemas + handlers), initializes empty history in `loop.py`;
(2) loop builds the system prompt (role + all tool JSON schemas + ReAct format convention) + user task →
`ollama.chat(model, messages, tools=[...])`; (3) model returns `Thought: I need search results first` +
`tool_calls: [web_search(query)]` → loop validates args against the schema → dispatches
`registry["web_search"](args)` → observation string appended; (4) loop re-prompts WITH the observation →
model reasons (`Thought: have results, now saving`) → `tool_calls: [write_file(...)]` → dispatch → observe;
(5) loop re-prompts → model emits `Final Answer: saved N findings to out.md` → return answer + write
`trace.jsonl` via `trace.py` (every thought, call, args, result, ms). Narrate YOUR saved trace line by line —
that's the definition-of-done demo.

**Q3. Why build the loop framework-free first instead of starting with LangChain/LangGraph?**

**Answer:** Because the framework hides exactly the decisions interviews probe. Hand-rolling `loop.py` forces
you to answer: how is the prompt assembled each iteration (and how history growth eats context), how are
`tool_calls` parsed and args validated (and what happens on malformed output), where observations re-enter
(the message-role choice matters), and where termination is enforced. After building it raw, a framework reads
as "prebuilt answers to problems I hit" rather than magic — and your trace inspection (definition of done)
is trivially clear because you own every line that produced it. Record the specific bug you only understood
by owning the loop (mine candidates: history-role confusion, arg-validation gaps, max-steps placement) —
that's the story that justifies the approach.

---

## Part 2: The ReAct Loop — "Reason, act, observe"

**Q4. Explain ReAct step by step. What does each phase contribute that the others can't?**

**Answer:** ReAct = Reason → Act → Observe, interleaved until done. **Reason** (`Thought:`): the model plans
the next step IN WRITING, conditioned on all prior observations — this is where adaptation lives (an early
search result changes the plan; a fixed chain-of-thought can't pivot). **Act**: the model emits ONE tool call
with concrete args — commitment to a falsifiable action, not more musing. **Observe**: YOUR runtime executes
and returns the result (or error) as text — the only phase grounded in reality; everything else is prediction.
Loop. The interleaving is the point: thought-without-action drifts, action-without-thought thrashes,
observation-without-loop is just a pipeline. Your error-recovery trace (Thought: "that path failed, trying…"
→ corrected Action → success) is the canonical ReAct specimen — keep it annotated.

**Q5. Native function-calling (`tools=` param) vs prompting the model to emit JSON actions — what's the difference, and why does it matter?**

**Answer:** Native calling: you pass tool schemas via the API's `tools=` parameter; the model returns a
structured `tool_calls` object parsed by the provider runtime, and decoding is constrained toward valid calls.
Prompt-parsed: you describe tools in prose and regex-parse free text hoping for `{"action": ...}` — fragile
to fences, commentary, and schema drift. Difference in reliability is large: your model-swap experiment (Q12)
likely shows the weaker Ollama model emitting fake JSON instead of `tool_calls` — that's the failure mode
native calling eliminates. Rule from Phase 1 JSON mode, repeated here: decoding-level constraints beat
prompting hope. If a model can't do native calls, switch MODELS (you recorded which failed) — don't build
regex scaffolding around a weak model.

**Q6. How does history management work across iterations, and what breaks as tasks get long?**

**Answer:** Each iteration appends (thought, action, observation) to the messages list, so the prompt GROWS
monotonically — step 8's prompt contains steps 1–7 verbatim. What breaks: context-window pressure (long tool
outputs, especially web pages, crowd out the original task — the model "forgets" the goal mid-run; your
over-long observation runs show this), cost growth (every step re-sends all prior steps — tokens scale
quadratically in task length), and distraction (stale observations get attended to as if current). Mitigations
you should have tried or can name: truncate/summarize old observations, cap observation size per tool (search
returns top-3 snippets, not full pages), and re-anchor the goal (repeat the task in each user turn). This is
the baby version of Project B's context-engineering problem — name the connection.

---

## Part 3: Tools — "Schemas are the selection mechanism"

**Q7. What is tool-calling mechanically, and why do tools need JSON schemas?**

**Answer:** Tool-calling = the model emits a structured invocation (`name` + `arguments`) instead of prose;
the runtime validates, executes, and returns text. The JSON Schema per tool (`name`, `description`,
`parameters` with types/required/enums) serves THREE consumers: (a) the RUNTIME validates args before
execution (wrong types → clean error observation, not a crash); (b) the MODEL reads `description` to choose
the right tool — selection happens by reading prose, so description quality IS routing quality (your
experiment Q9 proves this); (c) the PROVIDER uses the schema to constrain decoding toward valid calls.
Without schemas you'd parse fragile natural language ("please search for…") with regexes — unmaintainable
past two tools. Your `tools.py` registry (schema + handler + error contract per tool) is the executable
version of this answer.

**Q8. How do you write a tool description that the model actually selects correctly?**

**Answer:** State WHEN, not just WHAT. Bad: `"does file stuff"`. Good: `"reads a UTF-8 text file under
workdir; use when the task references a local file by name; returns file contents or ERROR with available
files on miss."` Ingredients: trigger conditions ("use when…"), scope bounds ("under workdir"), input
contract (path relative, UTF-8), and failure shape (what the observation looks like on miss — the model
pre-plans around known errors). Your description-weakening experiment (Q9) is the proof: same tools, vague
description, mis-selection rate jumps — restore precision, rate recovers. In interviews: "tool selection is
prompt engineering on the description field, and I measured the causal effect."

**Q9. You deliberately weakened a tool description and re-ran tasks. What happened, exactly?**

**Answer:** (Quote YOUR numbers.) Expected shape: with precise descriptions, 3 file-tasks route to
`read_file`/`write_file` correctly; with "does file stuff," the model mis-selects (calls `web_search` for a
local file, or hallucinates args the vague schema doesn't constrain) on ≥1 of 3. Restore precision → correct
routing returns. Conclusion: descriptions ARE the routing layer — no separate classifier exists in a ReAct
agent; the supervisor/router of Projects B is what you build when description-routing stops scaling. This
single experiment answers "why do schemas matter" better than any definition.

**Q10. Errors as observations — what does that mean in code, and show me a rescue from YOUR traces.**

**Answer:** In code: every tool handler is wrapped so exceptions become strings —
`try: return handler(args) except X as e: return f"ERROR: {what} — {how to fix}"` — and that string is
appended as the observation, so the model REASONS about it next thought. Example shape from your traces:
`Action: read_file("notes.md")` → `Observation: ERROR: file not found: notes.md — available: NOTES.md,
out.md` → `Thought: wrong case, retrying with NOTES.md` → `Action: read_file("NOTES.md")` → success.
Design rule: error strings must contain the FIX (available files, expected format, retry hint) — a bare
"failed" observation confuses the model further (you have one of those too — quote the confusion it caused).
A crash or give-up on first error is a Phase-3 failure; a visible Thought→corrected-Action→success is the
passing specimen. This pattern reappears as Project B's retry loop and RAG-B's self-correction — name that.

---

## Part 4: Guards & MCP — "Termination, safety, and the protocol"

**Q11. Why a max-steps guard? What EXACTLY goes wrong without it?**

**Answer:** A confused agent loops: tool A fails → model retries A with identical args → fails → retries —
each cycle burning an LLM call + tool execution, forever. Observed triggers: ambiguous task with no progress
signal, error observations the model can't parse, two tools whose descriptions both match so it ping-pongs.
`--max-steps 10` bounds worst-case cost (10 LLM calls + 10 tool executions, known upfront) and forces a
verdict: on exceed, terminate with the partial trace (your `--max-steps 2` break-run demonstrates: readable
truncation, not a hang). Production generalizes this to budgets (per-task spend caps), per-tool timeouts, and
loop detection (identical action ×3 → force-stop with note). "The guard converts unbounded spend into a
debuggable trace" is the line.

**Q12. Model swap: same tasks, two Ollama models. What did you learn about tool-use ability?**

**Answer:** (Quote YOUR table.) Expected shape: your primary model (`qwen3.5:4b`) uses native
`tool_calls`, needs fewer steps, passes multi-step tasks; a weaker/plumbing-tier model emits fake JSON, wastes steps
re-trying malformed calls, fails error-recovery. Columns: native-call compliance (tool_calls vs free-text),
avg steps per bucket, pass/fail. Conclusion with teeth: tool-use is a MODEL CAPABILITY, not just scaffolding —
below a competence floor no amount of prompt engineering rescues the agent, and your minimum-viable-model
finding (name it) is a deployment constraint. This also explains why hosted frontier models dominate agent
benchmarks: the loop is commoditized, the decider isn't.

**Q13. What is MCP and how is it different from the in-process tools you started with?**

**Answer:** MCP (Model Context Protocol) is a standard CLIENT–SERVER contract for tools: your tool runs as an
MCP SERVER (separate process, stdio/SSE transport, per the MCP SDK), exposing tool definitions + handlers;
the agent is a CLIENT that discovers schemas and invokes over the protocol. In-process calling (`tools.py`
functions called directly) is a function call in one Python process. Differences: MCP decouples tool from
agent — the server can be another language, another machine, shared by many agents; it standardizes discovery
(client asks "what tools exist?" instead of importing your module); it adds a hop (your measured +Xms per call
— quote it) plus operational surface (server must be RUNNING — your server-down break-run proves the failure
mode). "USB-C for AI tools vs hard-wiring each one": USB-C costs a connector and a cable, buys
interchangeability. Your `--mcp` flag runs the IDENTICAL task both ways — that A/B is the whole argument.

**Q14. When does MCP earn its overhead, and when is in-process the right call?**

**Answer:** MCP earns it when: tools are shared across agents/clients (one filesystem server, many agent
processes), tools live in another language or sandbox (untrusted code execution isolated by process boundary),
or the tool has an independent lifecycle (versioned/deployed separately from the agent). In-process wins when:
single agent, same language, same repo — the hop adds latency and a failure mode for zero decoupling benefit
(your pass-table likely shows parity on correctness with +latency on MCP — that's the honest result). Security
angle: MCP's process boundary is a containment primitive (a compromised tool server doesn't own the agent's
memory) — but the server is also a new attack surface (malicious tool descriptions = prompt injection INTO the
agent; Phase 3 guardrails take this up — name the handoff). "Use MCP at boundaries, in-process inside them."

---

## Part 5: Debugging & Production — "Traces, cost, and what's next"

**Q15. The agent fails a task. What is your debugging procedure, in order?**

**Answer:** (1) Open the trace — classify FIRST: wrong tool selected (description/prompt bug), right tool wrong
args (schema/validation bug), tool errored (tool implementation bug), loop/correction failure (observation
unhelpful or max-steps hit), or correct actions but bad final synthesis (generation bug). (2) Reproduce with
overrides: force the right tool via a narrowed registry, re-run — if it passes, the bug is selection, not
capability. (3) Fix at the right layer: mis-selection → rewrite the DESCRIPTION (not the loop); bad args →
tighten schema + validation messages; unrecoverable errors → enrich the ERROR string with the fix; thrash →
adjust max-steps or add loop detection. (4) Add the failing task to `evals/tasks.md` as a regression. The
meta-lesson: traces make agent bugs LOCALIZABLE — without `--trace` every failure is "the agent is dumb."

**Q16. Over-triggering: the model calls tools for a haiku. Why does that happen and how do you fix it?**

**Answer:** Your no-tool bucket catches this: task needs zero tools, model calls one anyway (search before
writing a poem). Causes: system prompt over-emphasizes tool use ("you HAVE tools, USE them" framing), no
"answer directly when possible" instruction, or temperature high enough to sample the action path. Fixes:
explicit direct-answer convention in the system prompt ("if no tool helps, answer directly — zero calls is a
valid trajectory"), few-shot no-tool example, and scoring zero-call correctness in your table (a pass WITH an
unnecessary call is a QUALITY failure, not a pass — record it as such). Production version: unnecessary calls
are pure cost (LLM + tool + latency), so over-triggering rate is a cost metric, not just correctness.

**Q17. What breaks at 10k requests/day that works fine on your laptop?**

**Answer:** Same loop, new constraints: per-task COST (each step = LLM call; your avg-steps × per-call price =
unit economics — multi-step tasks at 6 steps × frontier-model pricing need budgets); LATENCY tail (sequential
LLM calls can't parallelize naively — independent tool calls SHOULD batch, yours don't yet); CONCURRENCY
(one loop per request → connection pooling, rate limits on `web_search`/API tools, the MCP server as a shared
bottleneck); SAFETY (sandboxed `write_file` to workdir was a toy boundary — production needs auth, audit logs
of every action, and human gates before irreversible tools — Project B's gate is the prototype); OBSERVABILITY
(trace.jsonl becomes a span pipeline: per-step latency, tool error rates, over-trigger rate dashboards). The
loop shape survives; every stage gets metered, bounded, and gated. This is the agentic-system-design gap topic
from the roadmap — name it explicitly.

**Q18. Single agent (this project) vs supervisor team (Project B) — when is one loop enough?**

**Answer:** One ReAct loop suffices when: one role (search-then-write needs no planner/critic split), short
horizon (≤ ~5 steps fit comfortably in context with full history), single quality bar (no adversarial review
needed). The team earns its complexity when: roles CONFLICT (writer optimizes fluency, critic optimizes
correctness — one prompt can't hold both sharply), horizon is LONG (specialists see slices, not the whole
history — context economics), or quality needs REDUNDANCY (critic catches writer errors — your gate-ablation
defect in Project B is the receipt). Your Project B cost-comparison run (single agent vs team on one brief:
tokens, wall-clock, criteria met) quantifies it — preview that result here. Rule of thumb: start single,
split when the trace shows role-confusion (model planning while it should be executing) or context bloat.

---

## How to Use These Questions

1. **Narrate from traces** — every answer points at a `--trace` excerpt: the rescue, the misroute, the MCP A/B.
2. **Quote the tables** — pass rates per bucket, steps, model-swap deltas, MCP hop ms. Numbers or it didn't happen.
3. **Demo the breaks** — max-steps kill, server-down, sandbox escape attempt: live narration beats definitions.
4. **Connect forward** — error-as-observation → retry loops; history bloat → context engineering; MCP servers → guardrail surface.
