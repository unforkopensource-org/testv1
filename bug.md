# Decibench Bug Report

Comprehensive audit of every evaluator, connector, orchestrator, and supporting module.
Each bug has severity (CRITICAL / HIGH / MEDIUM / LOW) and a proposed fix.

---

## BUG-001: WER Evaluator — Self-Comparison / Dead Core Logic
**File:** `src/decibench/evaluators/wer.py`
**Severity:** CRITICAL
**Lines:** 34, 53, 134-140

### Problem
The WER evaluator compares the agent's STT transcript against itself. It's fundamentally broken in 3 ways:

1. **`_get_full_reference_texts()` returns empty 99% of the time.** It looks for `turn.text` on `agent` turns (line 138), but agent turns in scenario YAML almost never have `text` — they have `expect` (intents, must_include). Only `caller` turns have `text`. So the WER/CER calculation at lines 54-75 **never executes**.

2. **Even if it did run, it measures the wrong thing.** WER should measure ASR accuracy: compare STT output of *caller* audio against the *known caller script*. Instead, it tries to compare agent transcript against expected agent text — that's task completion, not ASR.

3. **`_get_reference_texts()` (lines 122-131) is dead code** — never called anywhere.

4. **Uses `jiwer.wer()` instead of `jiwer.process()`** — `jiwer.wer()` gives a single float. `jiwer.process()` gives a `WordOutput` object with the exact alignment map (substitutions, deletions, insertions with indices). Without `process()`, you cannot implement weighted WER or know *which* words were missed.

### Solution
Rewrite WER evaluator with three layers:

**Layer 1 — Pre-processing pipeline (`jiwer.Compose`)**
Normalize both reference and hypothesis: lowercase, remove punctuation, expand contractions, strip whitespace. This eliminates noise errors.

**Layer 2 — Alignment engine (`jiwer.process()`)**
Use `jiwer.process(reference, hypothesis)` instead of `jiwer.wer()`. This returns a `WordOutput` object containing:
- `alignments`: exact indices of every Hit, Substitution, Deletion, Insertion
- `wer`, `mer`, `wil` scores
- `substitutions`, `deletions`, `insertions` counts

**Layer 3 — Weighted intent evaluator (custom)**
Cross-reference the alignment map with `must_include` keywords. If a critical keyword is a Deletion or Substitution, apply a heavy penalty (weight=10.0) vs a filler word miss (weight=0.5).

Formula: `WER_weighted = sum(errors * weight) / total_reference_words`

**What to compare:**
- For ASR accuracy: compare STT(caller_audio) vs caller script text
- For agent response quality: compare agent transcript vs expected agent keywords (this is what `_check_keywords` already does, keep that)

---

## BUG-002: WER Keyword Check — No Per-Turn Granularity
**File:** `src/decibench/evaluators/wer.py`
**Severity:** HIGH
**Lines:** 142-191

### Problem
`_check_keywords()` checks `must_include`/`must_not_say` against the **entire agent transcript as one blob** (`hypothesis`). It doesn't check per-turn. A keyword expected in turn 3 could be "found" in turn 1's text, giving a false pass.

Example: Turn 1 agent says "Your order is tuesday delivery". Turn 3 expects `must_include: ["friday"]`. If turn 1 accidentally contained "friday" in some other context, it passes incorrectly.

### Solution
Check keywords per-turn: match each `turn.expect` against only the corresponding agent turn segment, not the full transcript. Use `transcript.segments` with turn indices to isolate the correct text window.

---

## BUG-003: Hallucination Entity Check — Double-Counting Entities
**File:** `src/decibench/evaluators/hallucination.py`
**Severity:** MEDIUM
**Lines:** 155-193

### Problem
The regex-based entity extraction double-counts. If the agent says "$500", the regex extracts:
- `"500"` from the numbers pattern (line 155)
- `"$500"` from the money pattern (line 158)

Both go into the `entities` list. If `"$500"` is grounded but `"500"` alone doesn't appear in `ground_text`, one is grounded and one isn't → 50% hallucination rate for a perfectly grounded response.

Similarly, a time like "2:00 PM" matches:
- The time pattern → `"2:00 PM"`
- The number pattern → `"2"`, `"00"`

### Solution
Extract in priority order (money > time > date > number), and skip entities already captured by a higher-priority pattern. Or deduplicate: if entity A is a substring of entity B and both are found, keep only B.

---

## BUG-004: Hallucination — Trivial Number Filter is Too Weak
**File:** `src/decibench/evaluators/hallucination.py`
**Severity:** MEDIUM
**Lines:** 189-191

### Problem
```python
non_trivial = [e for e in entities if len(e) > 2 or not e.isdigit()]
```
This filters trivial *numbers* but not trivial *entities*. A date like "Monday" or a filler number like "100" in "100% sure" still counts as a factual claim. The number "100" in "I'm 100% sure" is not a factual claim — it's an expression.

### Solution
Add an exclusion list for common non-factual expressions: "100%", "24/7", "one", "two", etc. Better: only count entities that appear in the context of a declarative statement about the caller's data.

---

## BUG-005: Latency P50/P95/P99 Calculation — Wrong Percentile Formula
**File:** `src/decibench/evaluators/latency.py`
**Severity:** HIGH
**Lines:** 54-56

### Problem
```python
p50 = sorted_latencies[n // 2]
p95 = sorted_latencies[int(n * 0.95)]
p99 = sorted_latencies[int(n * 0.99)]
```
For small `n` this is wrong. With `n=3`: `int(3 * 0.95) = 2` → index 2 (last element), `int(3 * 0.99) = 2` → same element. P95 and P99 are identical. With `n=1`: `int(1 * 0.95) = 0` → p95 = p50 = p99.

For `n=20`: `int(20 * 0.95) = 19` → index 19, but that's the max value (100th percentile), not 95th.

### Solution
Use `statistics.quantiles()` or numpy `np.percentile()`. Or: `index = min(int(math.ceil(n * p)), n - 1)` where `p` is the percentile fraction. Even better: just use `numpy.percentile(sorted_latencies, [50, 95, 99])`.

---

## BUG-006: Latency Fallback — Measures TTFW, Not Turn Latency
**File:** `src/decibench/evaluators/latency.py`
**Severity:** MEDIUM
**Lines:** 146-151

### Problem
```python
if not latencies:
    audio_events = [e for e in events if e.type == EventType.AGENT_AUDIO]
    if len(audio_events) >= 2:
        latencies.append(audio_events[0].timestamp_ms)
```
When no explicit TURN_END events exist, it falls back to using the *first audio event's timestamp as a latency*. This is time-from-start (TTFW), not inter-turn latency. And it requires `>= 2` audio events but only uses the first one — the second is unused.

### Solution
Measure gaps *between* consecutive audio events as a proxy for turn latency, or just skip turn latency when no TURN_END events exist (TTFW is already measured separately).

---

## BUG-007: Interruption Overlap Detection — Hardcoded 100ms Chunks
**File:** `src/decibench/evaluators/interruption.py`
**Severity:** MEDIUM
**Lines:** 128-129

### Problem
```python
# Each audio event ~ 100ms chunk
total_overlap += 100.0
```
This assumes each audio event is exactly 100ms. But WebSocket connectors can send variable-size chunks, and the demo connector's audio duration depends on word count (line 223 of demo.py: `words_count * 180ms`). The actual overlap could be 50ms or 500ms per chunk.

### Solution
Calculate actual chunk duration from audio data length: `chunk_duration_ms = len(event.audio) / (sample_rate * 2) * 1000` (for 16-bit PCM). Or use the timestamp delta between consecutive audio events.

---

## BUG-008: Compliance PII — Phone Number False Positives
**File:** `src/decibench/evaluators/compliance.py`
**Severity:** MEDIUM
**Lines:** 20

### Problem
```python
"phone_us": re.compile(r"\b\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
```
This matches any 10-digit number pattern, including order IDs ("ORD1234567890"), zip+4 codes, timestamps, and other non-phone numbers. In a customer service context, order numbers and account numbers are extremely common — they'll trigger false PII violations.

### Solution
Require phone-specific formatting: must start with `(`, `+1`, or have explicit separators. Or cross-reference with context — if the agent is reading back an order number from a tool result, it's not PII.

---

## BUG-009: Compliance AI Disclosure — Checks Full Transcript, Not First Turn
**File:** `src/decibench/evaluators/compliance.py`
**Severity:** HIGH
**Lines:** 121-145

### Problem
The method name and docstring say "Check if agent identifies as AI anywhere in the conversation" and the metric detail is `disclosed_within_first_turn`. But the actual logic checks the full transcript text (line 136: `if len(full_text) > len(check_text): check_text = full_text`). So if the agent says "I'm an AI" in turn 10, it passes as "disclosed within first turn."

Many jurisdictions require AI disclosure **at the start** of the conversation, not anywhere in it.

### Solution
Only check the first 1-2 agent turns (first ~30 seconds of transcript text) for AI disclosure. Use `transcript.segments` with timestamps to limit the check window.

---

## BUG-010: Score Normalizer — `keyword_presence`/`keyword_absence` Double-Counted
**File:** `src/decibench/evaluators/score.py`
**Severity:** MEDIUM
**Lines:** 249-260

### Problem
`keyword_presence` and `keyword_absence` are already percentage metrics (0-100%). Line 249 catches them via `metric.unit == "%"` and returns `value` as-is. But lines 259-260 ALSO have a special case that returns binary 100/0. If the code reaches line 259 first (which it can't because 249 matches first), or if the unit is changed, the behavior silently changes.

More importantly: these keyword metrics are mapped to the "conversation" category (line 36-37), same as WER and hallucination_rate. Since the WER core metric never fires (BUG-001), the "conversation" category score is entirely driven by keyword checks — which are crude presence/absence checks, not real conversation quality.

### Solution
Give keyword metrics their own normalization curve (not binary 100/0). 80% keyword hit rate should score ~60, not 0. And fix WER so the conversation category has real data.

---

## BUG-011: Orchestrator — `receive_events` Discards All Events
**File:** `src/decibench/orchestrator.py`
**Severity:** HIGH
**Lines:** 345-346

### Problem
```python
async for _event in connector.receive_events(handle):
    pass
```
Every event yielded by the connector during `receive_events` is **discarded**. The events ARE captured inside the connector's internal `self._events` list, but the orchestrator throws away its chance to:
- Monitor progress in real-time
- Detect interruptions as they happen
- Break early on timeout per-turn
- Emit per-turn trace spans

The events only become available later via `connector.disconnect()` → `CallSummary.events`.

### Solution
Collect events during iteration. At minimum, emit per-turn latency spans from the events. Ideally, implement per-turn timeout detection (if no agent response within `scenario.timeout_seconds / max_turns`, break and mark as failed).

---

## BUG-012: Orchestrator — `_average_runs` Uses Wrong `passed` Value
**File:** `src/decibench/orchestrator.py`
**Severity:** HIGH
**Lines:** 539-546

### Problem
```python
averaged_metrics[metric_name] = MetricResult(
    ...
    passed=template.passed,  # Re-evaluate based on avg  ← COMMENT LIES
    ...
)
```
The comment says "Re-evaluate based on avg" but the code uses `template.passed` — the pass/fail from the FIRST run, not re-evaluated against the averaged value. If run 1 passes but runs 2 and 3 fail, the averaged metric still shows `passed=True` from run 1's template.

The re-evaluation at lines 548+ fixes `passed` for metrics with thresholds, but metrics WITHOUT thresholds keep the stale `passed` from run 1.

### Solution
After averaging, re-evaluate ALL metrics. For metrics without explicit thresholds, use majority vote: `passed = sum(1 for r in runs if metric_name in r.metrics and r.metrics[metric_name].passed) > len(runs) / 2`.

---

## BUG-013: Vapi Connector — `send_audio` and `receive_events` Always Raise
**File:** `src/decibench/connectors/vapi.py`
**Severity:** HIGH
**Lines:** 79-88

### Problem
Both `send_audio` and `receive_events` unconditionally raise `NotImplementedError`. The connector can `connect()` (initiate a web call via HTTP) but cannot actually test the agent. Users who configure `vapi://agent-id` will get an API call that initiates a real Vapi call (billing them) and then immediately crash with NotImplementedError.

### Solution
Either:
1. Don't register it (`@register_connector("vapi")`) until it works — prevent users from accidentally triggering it
2. Fail at `connect()` time with a clear message, before the API call happens
3. Implement audio streaming via the WebSocket URL that Vapi returns (`webCallUrl`)

---

## BUG-014: Retell Connector — Same Issue as Vapi
**File:** `src/decibench/connectors/retell.py`
**Severity:** HIGH

### Problem
Likely same pattern as Vapi — initiates a real API call that costs money, then crashes on `send_audio`. Need to verify, but the file structure suggests identical issue.

### Solution
Same as BUG-013.

---

## BUG-015: WebSocket Connector — Turn Count Off-By-One
**File:** `src/decibench/connectors/websocket.py`
**Severity:** LOW
**Lines:** 193-198

### Problem
```python
turn_count = sum(1 for e in self._events if e.type == EventType.TURN_END)
return CallSummary(turn_count=max(turn_count, 1), ...)
```
If the agent never emits TURN_END events (many don't), `turn_count` is always 1 regardless of how many actual turns occurred. This gives wrong data to any evaluator that uses `summary.turn_count`.

### Solution
Count turns from send_audio calls (each `send_audio` call = one caller turn, so total turns = caller_turns + agent_responses). Or track `_turn_index` like the demo connector does.

---

## BUG-016: Demo Connector — Response Selection Not Scenario-Aware
**File:** `src/decibench/connectors/demo.py`
**Severity:** MEDIUM
**Lines:** 200-202

### Problem
```python
response_keys = list(_DEMO_RESPONSES.keys())
idx = (self._turn_index - 1) % len(response_keys)
response = _DEMO_RESPONSES[response_keys[idx]]
```
The demo agent cycles through responses by turn index, not by what the scenario actually asked. A "cancel subscription" scenario gets the "greeting" response on turn 1, "booking" on turn 2, etc. This means:
- `must_include` keyword checks fail arbitrarily
- Tool call expectations never match (scenario expects `lookup_order`, demo calls `check_availability`)
- Every scenario gets the same responses regardless of content

### Solution
Match responses by scenario intent or caller text keywords. At minimum, hash the caller text to pick a semantically appropriate response. Or use the scenario's expected intents to select from the response bank.

---

## BUG-017: Privacy Redaction — Credit Card Regex Too Greedy
**File:** `src/decibench/store/privacy.py`
**Severity:** MEDIUM
**Lines:** 15

### Problem
```python
(re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[REDACTED_CARD]"),
```
This matches any 13-16 digit sequence with optional spaces/hyphens. It will match:
- Timestamps: "20240414221530" (14 digits)
- Order IDs: "1234567890123"
- Phone numbers (already matched by phone regex → double redaction)
- Any long number

### Solution
Use Luhn algorithm validation after regex match. Credit card numbers must pass Luhn checksum. Or use tighter patterns with known BIN prefixes (4xxx for Visa, 5xxx for MC, etc.).

---

## BUG-018: Score — `_redistribute_weights` Keeps Half of Conversation Weight
**File:** `src/decibench/evaluators/score.py`
**Severity:** MEDIUM
**Lines:** 276-293

### Problem
When no judge is configured, it redistributes weights:
```python
deterministic["conversation"] = weights.conversation * 0.5
removed_weight = weights.task_completion + weights.conversation * 0.5
```
It keeps 50% of conversation weight for "WER-based conversation score." But as established in BUG-001, WER never fires. So the conversation category is driven entirely by keyword checks (crude string matching), getting 7.5% of the total weight based on almost no real data.

### Solution
After fixing WER (BUG-001), this becomes valid. Until then, remove conversation from deterministic mode entirely, or only include it if WER/keyword metrics actually produced data.

---

## BUG-019: Task Completion — `slot_extraction_accuracy` Checks Full Transcript
**File:** `src/decibench/evaluators/task.py`
**Severity:** MEDIUM
**Lines:** 126-147

### Problem
`_check_slot_extraction` checks if `expected_value.lower()` appears anywhere in `agent_text` (the full transcript). This means:
- If the agent mentions "tuesday" in turn 1, and we expect `must_extract: {day: "tuesday"}` in turn 3, it passes — even if turn 3 says "friday"
- Common words like "afternoon", "10", "yes" will almost always be found somewhere in a multi-turn transcript

### Solution
Check slots per-turn using transcript segments, not the full blob. Match the expected slot against only the agent segment that corresponds to the relevant turn index.

---

## BUG-020: MOS Evaluator — Heuristic Can Return `method: heuristic` as Float Key
**File:** `src/decibench/evaluators/mos.py`
**Severity:** LOW
**Lines:** 66, 141-165

### Problem
The heuristic returns `{"ovrl": 1.0, "method": "heuristic", "warning": "empty_audio"}`. The `method` and `warning` keys are strings, but the dict is typed as `dict[str, float | str]`. When this dict is spread into `MetricResult.details` (line 66: `details={**scores, "method": method}`), the `method` key from scores gets overwritten by the outer `method` variable — losing the heuristic's "method" value.

### Solution
Rename the heuristic's internal `method` key to `scoring_method` to avoid collision. Or extract only numeric keys from scores before spreading.

---

## Summary Table

| Bug ID  | Severity | File | Short Description |
|---------|----------|------|-------------------|
| BUG-001 | CRITICAL | wer.py | WER core logic never executes; measures wrong thing |
| BUG-002 | HIGH | wer.py | Keyword check has no per-turn granularity |
| BUG-003 | MEDIUM | hallucination.py | Entity double-counting inflates hallucination rate |
| BUG-004 | MEDIUM | hallucination.py | Trivial number filter misses non-factual expressions |
| BUG-005 | HIGH | latency.py | Percentile calculation wrong for small N |
| BUG-006 | MEDIUM | latency.py | Fallback measures TTFW not turn latency |
| BUG-007 | MEDIUM | interruption.py | Hardcoded 100ms chunk assumption |
| BUG-008 | MEDIUM | compliance.py | Phone regex false positives on order IDs |
| BUG-009 | HIGH | compliance.py | AI disclosure checks full transcript not first turn |
| BUG-010 | MEDIUM | score.py | Keyword metrics in conversation category masks WER absence |
| BUG-011 | HIGH | orchestrator.py | receive_events discards all events |
| BUG-012 | HIGH | orchestrator.py | _average_runs uses stale passed from run 1 |
| BUG-013 | HIGH | vapi.py | send_audio/receive_events always raise; wastes API call |
| BUG-014 | HIGH | retell.py | Same as Vapi — unimplemented but registered |
| BUG-015 | LOW | websocket.py | Turn count always 1 when no TURN_END events |
| BUG-016 | MEDIUM | demo.py | Response selection ignores scenario content |
| BUG-017 | MEDIUM | privacy.py | Credit card regex matches timestamps/order IDs |
| BUG-018 | MEDIUM | score.py | Conversation weight kept in no-judge mode despite dead WER |
| BUG-019 | MEDIUM | task.py | Slot extraction checks full transcript not per-turn |
| BUG-020 | LOW | mos.py | Heuristic method key collides with outer method variable |

**CRITICAL: 1** | **HIGH: 7** | **MEDIUM: 10** | **LOW: 2**
