# RepoPilot — Architecture Decision Log

This document records the key architectural and engineering decisions made during RepoPilot's development. Each decision includes its context, alternatives, rationale, and consequences.

The purpose is to make the project easier to maintain, evaluate, extend, and explain during technical interviews.

## Decision 1: Use a Hand-Rolled ReAct Agent Loop

**Status:** Accepted

**Context**

RepoPilot needs to coordinate language model responses, tool execution, and follow-up reasoning while maintaining control over the execution flow.

**Decision**

Implement a lightweight ReAct-style loop directly in Python in `src/repopilot/core/agent.py`.

**Alternatives considered**

* Use a full agent framework such as LangChain.
* Use a simple single-prompt interaction without tool execution.

**Rationale**

A custom loop makes the control flow explicit and easier to inspect. It also provides direct control over iteration limits, tool dispatch, error handling, and execution tracing.

**Consequences**

* The core remains lightweight and customizable.
* Agent behavior can be tested with mocked providers.
* Tool orchestration and error handling remain our responsibility.
* Future capabilities must be added without weakening execution limits.

## Decision 2: Separate the LLM Provider from the Agent Core

**Status:** Accepted

**Context**

RepoPilot should not be tightly coupled to one language model vendor.

**Decision**

Define a common `LLMProvider` interface in `src/repopilot/providers/base.py` and implement provider-specific behavior in adapter modules.

**Alternatives considered**

* Call the Gemini SDK directly from the agent.
* Implement separate agent logic for each model provider.

**Rationale**

The adapter pattern keeps provider-specific API details outside the core agent. It allows future providers to implement the same interface without requiring a complete rewrite of the orchestration logic.

**Consequences**

* The core can be tested independently of live API availability.
* Provider integrations can evolve separately.
* Each adapter must normalize responses consistently.
* A shared interface does not automatically guarantee identical behavior across different models.

**Current implementation**

Gemini is the active provider. Other provider files should be considered placeholders unless their implementations have been completed and tested.

## Decision 3: Use Gemini as the Initial LLM Provider

**Status:** Accepted for the initial implementation

**Context**

RepoPilot needs an LLM to interpret user questions, request available tools, and explain tool results. Development should remain practical on the available hardware and budget.

**Decision**

Use the Gemini API through a dedicated adapter while retaining the provider-independent architecture.

**Alternatives considered**

* Run a local model through Ollama.
* Integrate multiple hosted providers immediately.

**Rationale**

Starting with one hosted provider keeps initial integration focused and avoids the additional local memory and compute requirements of running a model on the development machine.

**Consequences**

* A working internet connection and valid API configuration are required for live model interactions.
* Availability, rate limits, latency, and model behavior depend on the selected service and model.
* The provider abstraction leaves room for additional adapters later.
* The initial implementation does not claim support for every provider.

## Decision 4: Begin with a Read-Only Git Tool

**Status:** Accepted

**Context**

An AI agent that interacts with repositories must be able to inspect repository state before it is trusted with operations that modify files or Git history.

**Decision**

Implement `git_status` as the first tool in `src/repopilot/tools/git_tools.py`.

The tool uses:

* `git status --short --branch`
* `git rev-parse --show-toplevel`

It uses argument-list subprocess execution, timeouts, and structured error responses.

**Alternatives considered**

* Begin with unrestricted shell execution.
* Allow the agent to edit files or execute Git write operations immediately.

**Rationale**

Read-only inspection establishes a narrow, testable boundary. It allows the agent's tool-use flow to be validated before introducing higher-impact capabilities.

**Consequences**

* The current tool cannot modify the repository.
* Unknown tool names and unexpected arguments are rejected.
* Future write-capable tools will require explicit authorization, policy checks, and appropriate tests.
* The current tool's restrictions do not replace a broader safety policy for future tools.

## Decision 5: Keep Execution Tracing Provider-Independent

**Status:** Accepted

**Context**

Agent execution needs to be observable for debugging, failure analysis, and future evaluation.

**Decision**

Implement tracing in `src/repopilot/core/tracing.py`, independently of the provider adapters.

**Alternatives considered**

* Keep logs only inside each provider adapter.
* Rely exclusively on unstructured console output.

**Rationale**

A shared tracer can record agent-level events consistently across provider implementations. Structured JSON also makes later analysis and evaluation easier.

**Consequences**

* Runs can produce structured event records and summary statistics.
* Trace output can be processed by future evaluation tools.
* Sensitive data must be minimized and redacted carefully.
* Current traces are diagnostic records, not a complete resumable checkpoint system.
* Token usage and monetary cost reporting depend on reliable provider usage data.

## Decision 6: Use Automated Tests Throughout Development

**Status:** Accepted

**Context**

Changes to agent orchestration, provider normalization, and tool execution can introduce regressions that may be difficult to identify through manual testing alone.

**Decision**

Use pytest to test the agent, tools, providers, and tracing components.

**Alternatives considered**

* Rely only on manual testing with the live LLM.
* Test only successful execution paths.

**Rationale**

Automated tests provide repeatable checks for expected behavior and selected failure scenarios without requiring a live model call for every test.

**Consequences**

* Core changes can be validated quickly.
* Mocked tests improve reproducibility.
* Passing tests demonstrate only the behaviors covered by those tests.
* Evaluation against realistic CI failures remains a separate milestone.

## Decision 7: Use a Modular Python Package with a CLI

**Status:** Accepted

**Context**

RepoPilot should be straightforward to install, run, test, and extend.

**Decision**

Use a `src/repopilot/` package layout, configure the project through `pyproject.toml`, and provide a CLI entry point.

**Alternatives considered**

* Keep the entire application in one Python script.
* Begin with a web interface before the core is established.

**Rationale**

A modular package makes component boundaries explicit and supports incremental development without requiring a web application.

**Consequences**

* Core logic, provider adapters, and tools have separate responsibilities.
* The CLI provides a simple development and demonstration interface.
* A web interface can be considered later if it serves a clear use case.

## Future Decisions to Revisit

The following areas will require additional decisions as RepoPilot evolves:

* How CI logs are acquired and sanitized.
* How root-cause findings are scored and evaluated.
* How proposed code changes are reviewed and approved.
* How safety policies restrict tools and consequential operations.
* How interrupted runs are recovered, if resumability is introduced.
* How evaluation datasets, model versions, latency, and costs are reported.

These decisions should be updated as the implementation evolves. Planned features must not be described as completed capabilities until they have been implemented and validated.
 