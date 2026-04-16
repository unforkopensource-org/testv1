# Decibench Docs

Decibench is local-first and intentionally narrow in v1.0. These docs
follow the truth model defined in [`plan.md`](../plan.md): every
user-facing capability is labeled **Shipped**, **Beta**,
**Experimental**, or **Planned**, and the labels match what the code
actually does.

| Topic                                                | Audience                              |
| ---------------------------------------------------- | ------------------------------------- |
| [Install](install.md)                                | Anyone getting started                |
| [Quick start](quickstart.md)                         | First five minutes                    |
| [WebSocket testing](websocket-testing.md)            | Real-time agents over WS              |
| [Local `exec:` testing](exec-testing.md)             | Agents you can spawn as a process     |
| [Production import + evaluation](import-and-evaluate.md) | Offline analysis of real calls   |
| [Replay to regression](replay-to-regression.md)      | Closing the loop                      |
| [Native connector status](native-connectors.md)      | Retell / Vapi / planned vendors       |
| [Dashboard / failure workbench](dashboard.md)        | Triage UI                             |
| [Bridge protocol](bridge-protocol.md)                | Native bridge wire contract           |
| [Honest limitations](limitations.md)                 | What v1.0 does **not** do             |

The machine-readable source of truth for feature status is
[`support-matrix.yaml`](support-matrix.yaml).
