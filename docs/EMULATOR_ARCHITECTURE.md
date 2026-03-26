# FranklinWH Cloud API Emulator (Future Architecture)

## 1. Vision & Purpose
As directly requested by the core maintainer, standard Pytest mocks are strictly insufficient for validating multi-node gateway traffic. We aim to construct a fully transparent, local synthetic `FranklinWH Cloud API Emulator` sandbox.

This standalone service will emulate the exact Java Spring Boot `@RestController` logic deployed by FranklinWH, allowing downstream integrators (`franklinwh-ha-integrator`) to test API payloads against a cryptographically structured backend without touching physical `aGate` hardware or bouncing live internet proxies.

## 2. Core Capabilities
The Emulator will achieve:
1. **Multi-Account & Multi-Site Simulation:** Transparent synthesis of heavily chained residential and commercial topographies. 
2. **Deterministic Failure Injection:** 
   * Simulate `401 Unauthorized` token revocations spanning exactly `N` seconds.
   * Modulate `429 Too Many Requests` concurrency ratelimiting to proof the `instrumented_retry` backoff.
   * Throw pseudo-random `503 Service Unavailable` latency spikes.
3. **Strict Schema Constraints:** Active `@NotNull` and schema typing intercepts. It will instantly crash if the `franklinwh-cli` (or Python client) issues a POST request without required body payloads (e.g., dropping dictionaries for `Content-Length: 0`).
4. **Proxy Isolation:** Complete isolation from the internet—simulating slow response streams, corrupted bytes, and split-brain Modbus integrations natively inside a Dockerized stack.

## 3. Implementation Pathway (TODO FUTURE)
* A separate uncoupled repository (e.g. `franklinwh-cloud-emulator`) likely built on FastAPI or Spring Boot strictly modeling the observed data topologies inside `tests/results/`.
* Exposing a Control Dashboard allowing integration engineers to dial gateway topologies (e.g. "Simulate 2 isolated aGates where one is 100% full and the other has a hardware fault").
* Updating this `franklinwh-cloud` library to accept a standard `base_url=http://localhost:8080/hes-gateway/` to cleanly re-route requests without rewriting logic wrappers.
