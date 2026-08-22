# ADR 0002 — LangGraph instead of CrewAI, AutoGen, or a hand-rolled loop

Status: accepted

## Context

The assessment workload has a specific, *known* shape:

1. Extract N obligations from a circular.
2. For each obligation independently: retrieve candidate policy clauses, judge
   the impact, verify the judgement is grounded, retrying the judge on failure.
3. Once all obligations are done, synthesise one memo.

Step 2 is embarrassingly parallel — assessing obligation 3 tells you nothing
about obligation 4. Step 3 is a fan-in. The retry in step 2 is a bounded loop
with a specific exit condition.

## Decision

Use LangGraph. `plan_assessment` fans out with a conditional edge returning a
list of `Send("assess_obligation", …)`, one per obligation; the findings key is
`Annotated[list, operator.add]` so concurrent workers merge rather than
overwrite; a token-cap node gates the fan-in before `synthesize_memo`.

## Alternatives considered

**CrewAI / AutoGen (conversational multi-agent).** Rejected. These frameworks
model coordination as agents *talking to each other* and deciding what to do
next. Our control flow is not open-ended — it is a fixed graph that we know in
advance. Paying for a negotiation the problem does not have means
non-deterministic control flow, tokens spent on inter-agent chat, and a
topology that cannot be asserted in a test. The graph here is a property of the
problem, not something to be discovered at runtime.

**A hand-rolled `asyncio.gather` loop.** Genuinely close, and the honest
alternative. Rejected for three specific things LangGraph gives us that we
would otherwise build: the `Send` fan-out with a typed state reducer (the
`operator.add` annotation is what prevents concurrent workers from clobbering
each other's findings — a subtle bug we would have to rediscover); a node
boundary that is a natural place to hang tracing, which is what makes
`agent_steps` a first-class feature rather than scattered logging; and a
declarative topology that a test can assert on.

**LlamaIndex.** Rejected: it wants to own retrieval, which we deliberately own
ourselves so the evaluation harness and the UI can share one measured code
path.

## Consequences

**What we gain.** The parallelism is declared, not orchestrated by hand. Every
node execution is traced uniformly. The topology is assertable — a test checks
the nodes exist and that `findings` carries an additive reducer.

**What it costs.**

- A dependency whose 0.x API still moves; `Send` and the reducer contract are
  the parts we rely on, and an upgrade could touch them.
- The per-(obligation, clause) verification retry lives *inside* the worker
  rather than as graph edges, because encoding it as edges would require the
  fan-out state to carry per-pair retry counters. So the graph does not show
  the whole control flow, and the loop bound is enforced in Python.
- Debugging a fan-out is harder than debugging a `for` loop: a failure inside
  one branch surfaces as a branch result, not a stack trace at the call site.
- Some conceptual overhead for a reader who has not seen LangGraph.
