# stanfordnlp/dspy — Domain Map
Last refreshed: 2026-05-18 (seed)

## Architecture in 5 sentences

DSPy treats an LLM pipeline as a *compiled program*: you write Python modules
that declare input/output contracts via Signatures, compose them with ordinary
control flow, and then hand the whole program to an Optimizer that synthesizes
few-shot demonstrations and/or natural-language instructions automatically.
The central abstraction is `dspy.Module` — a callable whose `forward()` method
chains any number of built-in predictors (Predict, ChainOfThought, ReAct, etc.)
and whose internal LM calls are transparently traced so the optimizer can read
and rewrite them.
Signatures are the unit of task specification: either a terse inline string
(`"context, question -> answer"`) or a class with typed `InputField` /
`OutputField` declarations including Pydantic models, making them both
human-readable and machine-parseable.
Optimizers (teleprompters) treat the metric function as the only ground truth
and improve the program by bootstrapping labeled traces, running random search
or Bayesian methods over instruction variants, or distilling everything into
fine-tuned weights.
The result is that prompt engineering is replaced by a feedback loop: write a
metric, provide ~10–200 labelled examples, run an optimizer, and DSPy rewrites
the prompts/demos for you.

## Key design choices (taste, not docs)

- **Separation of structure from content.** Signatures declare *what* a module
  does; optimizers decide *how* to phrase it. This means the same program can
  be reoptimized for a different LM or task without touching application code.

- **Optimizer as first-class citizen.** BootstrapFewShot generates demonstrations
  by running the teacher program on the trainset and keeping traces that pass the
  metric — no human annotation of chain-of-thought steps required.

- **MIPROv2 as the flagship optimizer.** It jointly searches over instruction
  text *and* few-shot examples using a Bayesian surrogate model, making it
  substantially more sample-efficient than grid or random search.

- **Lazy / optional dependencies by design.** Recent releases made numpy
  optional, replaced typeguard with stdlib, replaced xxhash with hashlib, and
  removed asyncer — the core is deliberately kept thin so DSPy can be embedded
  in constrained environments.

- **LiteLLM for provider abstraction.** Any LM reachable via LiteLLM is a
  first-class citizen; the framework itself is provider-agnostic.

- **Typed fields over free-form prompts.** OutputField supports `bool`,
  `list[str]`, `Literal[...]`, and Pydantic models, so the optimizer can
  validate outputs automatically rather than relying on fragile regex parsing.

- **Module-level context and async.** `dspy.context()` scopes configuration
  (active LM, temperature, etc.) per call stack, enabling concurrent async
  pipelines — though aiostream interop is a known rough edge.

## Current pain points (last 30 days, from PR / issue clustering)

- **Async concurrency hazards.** `dspy.context()` breaks inside
  `aiostream.stream.merge` (#8797); `ParallelEvaluate` shutdown has race
  conditions (#9574). The context-propagation model was designed for sync and
  is showing seams under heavy async use.

- **Pydantic/serialization fragility.** `MockValSer` TypeError during cached
  native tool processing (#9737) indicates the serialization layer is brittle
  at the Pydantic v2 boundary, especially around tool-call caching paths.

- **Deno / PythonInterpreter path parsing.** Commas in file-system paths break
  the `--allow-read` argument parser for the Deno-backed sandbox (#9749) —
  a niche but hard-to-work-around environment issue for RLM users.

- **ChainOfThought quality ceiling.** An open enhancement (#9646) tracks a
  request to rework the CoT implementation, suggesting the current reasoning
  injection (prepending a `reasoning` field) is too blunt for complex tasks.

- **Tree-of-Thoughts / Graph-of-Thoughts still missing.** Issue #1736 has been
  open a long time; the module library has not kept pace with reasoning-pattern
  research beyond ReAct and MultiChainComparison.

## Unique advantages

- **Automatic prompt compilation.** No other mainstream framework offers an
  optimizer that rewrites both instructions and few-shot examples end-to-end
  from a metric, without human-labeled CoT traces.

- **MIPROv2's Bayesian search.** Using a surrogate model over the instruction
  search space makes optimization viable with 200 examples in ~10 min / ~$2,
  versus manually tuning or running hundreds of LLM calls blindly.

- **BootstrapFineTune.** The same optimizer interface can distill a prompted
  program into fine-tuned weights, giving a clean continuum from zero-shot
  inference to fully fine-tuned models.

- **SIMBA / GEPA for self-reflection.** Newer optimizers (SIMBA uses mini-batch
  hard examples; GEPA reflects on program trajectories) push toward LLM-driven
  meta-optimization without human-in-the-loop prompt writing.

- **Typed I/O contract via Signatures.** Inline `"inputs -> outputs"` strings
  plus full Pydantic model support make it the most concise task-specification
  DSL in the ecosystem while remaining statically analyzable.

- **RLM (Recursive LM).** The sandboxed Python-execution module allows deeply
  nested LLM calls within a controlled environment — unique among popular
  agent frameworks.

## Deltas vs LangChain / ADK / pydantic-ai

| Dimension              | DSPy                                   | LangChain                          | Google ADK                        | pydantic-ai                        |
|------------------------|----------------------------------------|------------------------------------|-----------------------------------|------------------------------------|
| **Core abstraction**   | Compiled Module + Signature            | Chain / Runnable / LCEL            | Agent + Tool DAG                  | Agent + typed tool results         |
| **Prompt strategy**    | Optimized automatically by teleprompter| Hand-written templates (PromptTemplate) | Hand-written / Vertex tuning   | Hand-written system prompt         |
| **Few-shot**           | Auto-bootstrapped from metric          | Manual examples in templates       | Not a first-class primitive       | Not a first-class primitive        |
| **Optimization loop**  | Built-in (BootstrapFewShot, MIPROv2…)  | None built-in                      | None built-in                     | None built-in                      |
| **Typing**             | InputField/OutputField + Pydantic      | Partial (output parsers)           | Pydantic tool schemas             | Full Pydantic throughout           |
| **Async**              | Supported; context propagation fragile | First-class (LCEL async)           | First-class                       | First-class                        |
| **Provider**           | LiteLLM (any)                          | LiteLLM / many integrations        | Google-first, some others         | Any via model interface            |
| **Agent primitives**   | ReAct, RLM                             | AgentExecutor, LangGraph           | Full multi-agent runtime          | Single agent + tool loop           |
| **Fine-tuning path**   | BootstrapFineTune (built-in)           | Manual / external                  | Vertex AI tuning (external)       | Not provided                       |
| **Research pedigree**  | Stanford NLP, peer-reviewed (2024)     | Industry-driven                    | Google DeepMind                   | Community / Samuel Colvin          |

**Key takeaway:** DSPy's unique niche is *metric-driven prompt compilation* —
it wins whenever you care about systematic optimization over a dataset and are
willing to define a metric. LangChain wins on ecosystem breadth; ADK wins on
Google-infra integration; pydantic-ai wins on type-safety and simplicity for
single-agent tasks.
