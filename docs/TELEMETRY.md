# Telemetry & Usage Metrics

**This library collects no telemetry.** Neither `franklinwh-cloud` nor `franklinwh-cli` sends
usage data, analytics events or identifiers anywhere. The only network traffic it makes is to
the FranklinWH cloud API you point it at.

An earlier opt-in design that sent events to a third-party analytics service (PostHog) was never
completed and has been removed. Even with no identifiers in the payload, a third-party service
receives the user's IP address and client details with every request. That needs disclosure and
consent that a library shouldn't impose on the integrations built on it, including Home Assistant
compliance.

## How usage is measured instead

From sources that already exist and that users have already agreed to:

| Source | What it shows | Where |
|---|---|---|
| **GitHub** | Repository traffic (views, clones), stars, forks, release pages | Repository → *Insights* → *Traffic* (last 14 days) |
| **Home Assistant analytics** | How many installations use an integration built on this library, from users who opted in to Home Assistant's own usage analytics | [analytics.home-assistant.io](https://analytics.home-assistant.io) |

Neither involves any code in this library.

## Adding telemetry in future

Don't, without an approved plan that covers: opt-in only (off by default), a published list of
what's sent **and what any third party collects independently** (IP address, client details),
retention, and how to opt out. Integrations built on this library would inherit the disclosure
duty, so it must not be enabled from inside the library.
