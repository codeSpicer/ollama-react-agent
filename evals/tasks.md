# Eval tasks — write BEFORE any agent code (Phase 0)

Each task states its EXPECTED tool sequence. If you can't state it, the task is vague — rewrite it.
Tool names: `calculator` · `read_file` · `write_file` · `web_search` · `get_weather`.
Run with `--trace` once `loop.py` exists (W2); error-recovery tasks MUST show Thought → corrected Action → success.

## Single-tool (3)

- [ ] **S1 — arithmetic.** "What is 17 * 23?" → expected: `[calculator]`
- [ ] **S2 — local read.** "Read NOTES.md in the workdir and tell me what it says." → expected: `[read_file]`
- [ ] **S3 — JSON API.** "What is the current weather in Berlin? (52.52, 13.41)" → expected: `[get_weather]`

## Multi-step (3)

- [ ] **M1 — search then save.** "Search the web for DuckDuckGo HTML endpoint rate limits and save the findings to out.md." → expected: `[web_search, write_file]`
- [ ] **M2 — read, compute, write.** "Read prices.txt in the workdir, add up all the prices, and write the total to total.md." → expected: `[read_file, calculator, write_file]`
- [ ] **M3 — two searches, one file.** "Search the web for 'Ollama tool calling' and for 'Model Context Protocol stdio', then save a combined summary to compare.md." → expected: `[web_search, web_search, write_file]`

## Error-recovery (2) — first attempt SHOULD fail, agent must retry corrected

- [ ] **E1 — wrong-case path.** "Read note.md (lowercase) in the workdir and summarize it." Fixture on disk is `NOTES.md`, so the first call fails. → expected: `[read_file → ERROR, read_file → success]`
- [ ] **E2 — bad calculator arg.** "What is twelve times eight?" If the model calls `calculator("twelve*eight")` it gets an ERROR observation and must retry with digits. → expected: `[calculator → ERROR, calculator → success]`

## No-tool (2) — zero calls is the correct trajectory; any call is an over-triggering bug

- [ ] **N1 — haiku.** "Write a haiku about the sea." → expected: `[]`
- [ ] **N2 — general knowledge.** "In one paragraph, explain why the sky is blue." → expected: `[]`
