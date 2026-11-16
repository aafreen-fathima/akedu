# ADR-02: LLM access

**Status:** Accepted

**Options considered:** Ollama only; hosted only; gateway with both

**Decision:** Gateway (llm_gateway.py) with ollama, openai-compatible and heuristic providers, chosen by AKEDU_LLM_PROVIDER

**Consequences:** The PoC can compare providers on the same outlines; heuristic provider keeps CI and demos model-free

**Revisit if:** One provider clearly wins the PoC
