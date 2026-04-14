Voice agent testing: a complete technical reference for building an open-source framework
An open-source voice agent testing framework can realistically compete with the current crop of funded startups because every existing platform shares the same blind spots: none offer true end-to-end audio pipeline testing with open-source tooling, all rely on opaque LLM-as-judge scoring, and the market remains deeply fragmented across 14+ closed-source competitors with no interoperability. This document maps the entire competitive landscape, catalogs every testable API surface across 10 major voice platforms, and defines the complete metric taxonomy required to build a production-grade, best-in-class benchmarking framework.

AREA 1: Competitor platform analysis
The market clusters into four tiers of maturity
The voice agent testing space has exploded since mid-2024, with $100M+ in aggregate funding flowing into roughly 14 identifiable platforms. The market segments into: (1) dedicated YC-backed testing platforms (Hamming, Roark, Coval, Cekura, Bluejay), (2) general LLM eval platforms adding voice (Maxim, Braintrust+Evalion), (3) telephony-native testers (Sipfront), (4) platform-bundled testing tools (Retell Assure, Vapi Evals, LiveKit Testing), and (5) open-source attempts (voice-lab). No single platform covers the full stack from SIP signaling to conversation-level semantics.
Hamming AI — the current market leader
Company: Founded 2024, YC S24, ~8 employees, $3.8M seed led by Mischief. Claims 4M+ calls tested, 10K+ agents monitored.
Test execution model: PSTN/SIP calls (dial real phone numbers), WebRTC/WebSocket (direct LiveKit/Pipecat connection without SIP), and chat-based text testing. Supports one-click imports for Vapi, Retell, ElevenLabs, LiveKit, Pipecat, Hopper, Fluents, and OpenAI Realtime API. Load testing at 1,000+ concurrent calls with realistic accents and background noise.
Evaluation methodology: Two-step LLM-as-judge pipeline achieving 95–96% agreement with human evaluators. Audio-native evals analyze audio directly, not just transcripts. Holistic goal-based evaluation (did the caller accomplish their goal?) rather than turn-by-turn script matching. Custom scoring prompts called "scorers" with ScoreType.ACCURACY_AI and other types. Hume AI integration for emotional/sentiment scoring.
Metrics: Claims 50+ built-in metrics including WER (target <5% clean, <10% noisy), turn-level latency, MOS, intent recognition (5-metric framework), prompt compliance rate per segment (greeting/verification/transaction/closing), task completion, repetition detection, interruption handling, scope creep detection, and sentiment analysis. Organized into a 4-Layer Quality Framework: Infrastructure → Agent Execution → User Reaction → Business Outcome.
SDK/API: TypeScript (@hamming/hamming-sdk), Python SDK. REST API at POST https://app.hamming.ai/api/rest/v2/call-logs with Bearer token auth. Native CI/CD via hamming-ci-workflow GitHub Actions. LangChain integration via HammingCallbackHandler.
Pricing: Opaque, usage-based, contact sales. No self-serve free trial. Partner offer of 100 free test calls for Retell customers.
Compliance: SOC 2 Type II, HIPAA with BAA, US/EU data residency, SSO, RBAC.
Blind spots: No public pricing, no self-serve trial, docs partially gated, no open-source core, small community (no Discord, 17 GitHub followers on HammingHQ org with max 32 stars on any repo).
Roark AI — production replay differentiator
Company: YC W25, ~3 employees, ~$2M pre-seed from F-Prime Capital, True Ventures, Liquid 2 Ventures. Claims 10M+ minutes processed. Positions as "Datadog for Voice AI."
Key differentiator: Production call replay that clones the original caller's voice and re-simulates from divergence points. Failed calls automatically become regression tests. Graph-based scenario design with branching edge cases.
Evaluation: Dual approach — deterministic logic (exact calculations/thresholds) combined with LLM-as-judge. Evaluators are composable "blocks" that mix both methods. Hume AI integration for emotion detection (frustration, confusion, happiness).
Metrics: 40+ built-in including latency (call and turn level), instruction-following compliance, repetition, sentiment per speaker, emotion analysis, goal completion, conversation flow analytics. Multi-speaker analysis up to 15 speakers. Transcription in 50+ languages with WER as low as 8.6%.
SDK/API: Node.js (roark-analytics npm), Python (roark-analytics pip), Go SDK. All Apache-2.0 licensed. REST API with Bearer token auth. One-click integrations for Vapi, Retell, LiveKit Cloud, Pipecat Cloud, Voiceflow.
Pricing: Transparent credit-based: Startup $500/mo (50K credits, ~5K call minutes), Growth $1,200/mo (120K credits, ~12K minutes), Enterprise custom. SOC2/HIPAA only on Growth+.
Blind spots: Very small team (3 people), replay methodology breaks when agent responds differently, no free tier ($500/mo minimum), no red-teaming features, no chat agent testing, HN feedback noted pricing significantly higher than alternatives.
Coval AI — Waymo simulation philosophy
Company: Founded 2024 by Brooke Hopkins (ex-Waymo eval infrastructure lead), YC-backed, ~10 employees, $3.8M raised ($3.3M seed led by MaC Venture Capital with General Catalyst participation).
Approach: Brings autonomous vehicle simulation philosophy to voice agents. Simulates thousands of conversation flows using synthetic LLM-powered personas with configurable voice, accent, tone, and emotion. Supports both text and audio-in/audio-out simulation.
Evaluation: Hybrid model combining built-in system metrics (latency, interruptions, speech tempo), custom LLM-as-judge metrics, tool call validations (tracks when/how/why tools were called), and workflow validations. Probabilistic evaluation philosophy — some features may accept 80% success, others 99.9%.
Metrics: Latency (e.g., 1.09s shown), resolution rate (94% shown), missing disclosure count, audio duration, turn count, intent recognition, time to first audio byte, WER, speech tempo.
SDK/API: REST API, Rust CLI (github.com/coval-ai/cli), MCP Server for AI assistant integration, GitHub Actions integration. Python examples at github.com/coval-ai/coval-examples. Also publishes voice AI benchmarks for TTS/STT models.
Pricing: Core $300/mo, Scale $999/mo, Enterprise custom. Free trial with personalized onboarding.
Blind spots: No public pricing page on website, very small GitHub footprint (max 4 stars), no compliance certifications documented publicly, limited integration partnerships (only Pipecat and Cisco/Webex documented), no Reddit/HN community presence.
Cekura (formerly Vocera) — three-layer evaluation engine
Company: YC F24, founded by three IIT Bombay alumni (Tarush Agarwal ex-quant finance, Shashij Gupta ex-Google Research NLP with 50+ citation paper on AI testing from ETH Zurich, Sidhant Kabra ex-consulting). $2.4–2.9M raised. Claims 75+ customers including Five9, HighLevel, Twin Health, Jotform, MindTickle. #1 on Product Hunt, hunted by Garry Tan.
Critical technical distinction: Explicitly NOT purely LLM-as-judge. Three-layer evaluation: (1) Heuristic models for audio-specific signals (gibberish detection, interruption tracking, pitch analysis), (2) Statistical models for quantitative metrics (latency, timing), (3) LLM-as-judge for semantic evaluation (instruction following, hallucination, empathy). Full-session evaluation, not turn-by-turn — catches cascading failures across conversation.
Test execution: Makes real phone calls to agents. Parallel calling with multiple simultaneous tests. Auto-generates test cases from agent descriptions. Production call replay with automatic test case extraction. Mock tool platform with defined schemas/behaviors for isolated testing. Deterministic structured test cases as "conditional action trees."
Red teaming: Dedicated product covering jailbreaking, bias/fairness, toxicity, PII/data leakage. Multi-turn red teaming achieves 92.7% success rate vs. 19.5% for single-turn.
Metrics: Gibberish detection, interruption tracking, latency, sentiment, pitch, empathy, responsiveness, hallucinations, instruction following, ringing duration, success rate, call volume trends, call end reasons. 10+ built-in metrics running on every call automatically.
SDK/API: Full API reference at docs.cekura.ai/api-reference/. MCP support with 84+ tools. Claude Code skills for building tests. Integrations: Retell, Vapi, ElevenLabs, LiveKit, Pipecat, Synthflow, Bland, Cisco, SIP, chat, SMS, WhatsApp.
Pricing: Developer $30/mo (750 credits, 10 concurrent calls, 7-day free trial with 300 credits, no credit card). Enterprise custom with SOC 2, HIPAA, GDPR, self-hosting option.
Blind spots: Small team, credit-based pricing opacity, self-hosting Enterprise-only, community still small (25 HN points on recent launch).
Maxim AI, Braintrust, and Evalion — general eval platforms adding voice
Maxim AI (getmaxim.ai): $3M seed, founded by ex-Google Assistant NLP engineer and ex-Postman engineer. Full-stack eval platform (experimentation, simulation, observability, Bifrost LLM gateway). Voice capabilities are observability-only via LiveKit integration — no voice simulation engine. Free tier available. Pricing: $29/seat/mo (Professional), $49/seat/mo (Business). SOC 2 Type II, ISO 27001, HIPAA, GDPR. Unique HTTP endpoint black-box testing capability.
Braintrust (braintrust.dev): The heavyweight — $80M Series B at $800M valuation (Feb 2026, led by ICONIQ, with a16z and Greylock). Customers include Notion, Stripe, Cloudflare, Ramp, Dropbox. Open-source autoevals library (807 GitHub stars, MIT license). Three-component eval model: Dataset → Task → Scorers. 25+ built-in AutoEval scorers (Factuality, Relevance, Helpfulness, Safety, etc.). No built-in voice simulation — delegates entirely to Evalion. Voice support limited to audio attachment debugging, OpenAI Realtime API evaluation, and custom voice scorers. Pricing: Starter free (1GB, 10K scores), Pro $249/mo. GitHub Action for CI/CD.
Evalion (evalion.ai): Independent voice simulation company partnering with Braintrust. Founded by Miguel Andres (PhD, 25+ years, ex-Google). Published academic paper benchmarking against competitors (arXiv:2511.04133): Evalion scored 61.0 overall vs. Coval 48.9 vs. Cekura 43.0 in simulation quality (human-judged). F1-score 0.92 on evaluation accuracy vs. ~0.73 for competitors. HIPAA and SOC 2 compliant. No public pricing, no GitHub presence, demo-gated. Self-authored benchmark = potential conflict of interest, though methodology uses 21,600 human judgments.
Bluejay, Sipfront, and Leaping AI — specialized entrants
Bluejay (getbluejay.ai): YC S25, $4M seed led by Floodgate with PeakXV. Crossed $100K ARR in under a month during YC. Customers include Google, 11x, Zocdoc. Pure QA platform with "Digital Humans" — configurable synthetic personas across 500+ variables (accents, noise, emotions, behavioral patterns). Claims to compress 1 month of interactions into 5 minutes. Integrations: Bland, ElevenLabs, LiveKit, Pipecat, Retell, Vapi, SIP, WebSocket. Metrics: latency (P50/P95/P99), accuracy per variable, hallucination, tool calls, interruptions, sentiment. No public pricing, no GitHub repos.
Sipfront: Vienna-based, €1.8M seed (Jan 2026). The only platform operating at the full telephony stack: SIP signaling validation, RTP media path integrity, DTMF testing, MOS scoring (via ViSQOL), jitter/packet loss measurement, post-dial delay, one-way audio detection, codec negotiation testing (G.711, Opus, AMR). REST API at https://app.sipfront.com/api/v2/tests/run with Basic Auth. AI voice bot testing via custom baresip module interfacing with OpenAI Realtime API. 26 GitHub repos including baresip fork and ViSQOL docker build. Blind spot: conversational AI evaluation less sophisticated than pure-AI testers.
Leaping AI: YC W25, $4.7M raised, Berlin/SF. Not a testing platform — it's a voice agent platform with built-in QA and self-improvement. Claims autonomous post-call evaluation with automated prompt adjustment and A/B testing. Cannot test agents on other platforms. Marketing-heavy "self-learning" claims lack technical transparency.
Platform-native testing tools have significant limitations
Retell Assure (launched Dec 17, 2025): Post-deployment monitoring of 100% of calls (vs. traditional 1–2% sampling). Creates QA Cohorts with configurable agent/date/duration/sampling filters. Measures latency, interruptions, hallucinations, sentiment swings, tool-call errors, KB accuracy, resolution rate. Free for first 100 minutes per workspace. Limitation: Audio Simulation (batch audio testing) still "Coming soon." Pre-deployment simulation testing is text-only.
Vapi Evals: Two systems — original Test Suites (dashboard-only, up to 50 test cases, 15-min call limit) and newer Evals framework with full API (POST /eval/run). Mock conversation JSON format with three judge types: exact match, regex, AI judge. Tool call validation for both function name and arguments. CI/CD via CLI. Limitation: chat.mockConversation type only — no voice evals via API, no noise/accent/interruption testing.
LiveKit Agents Testing Framework: Most developer-native approach. Full pytest/Vitest integration with fluent assertion API (RunResult class). is_message(), is_function_call(name=, arguments=), judge(llm, intent=) assertions. Tool mocking via mock_tools(). Multi-turn testing with automatic history. CI/CD works without LiveKit API keys. Limitation: text-only — does not test audio pipeline (STT, TTS, turn-taking, latency, WebRTC).
voice-lab (github.com/saharmor/voice-lab): 163 stars, 13 forks, Apache-2.0, Python. Custom metrics via JSON, LLM-as-judge scoring, model comparison across LLMs, persona-based testing. Text-only — voice analysis listed as contribution idea. Single-maintainer, no parallel execution, no CI/CD, no audio analysis. Essentially a prompt testing tool, not a voice testing framework.
Competitive landscape summary table
Platform
Funding
Test Method
Metrics
Entry Price
Voice Sim
Open Source
Hamming
$3.8M
PSTN/SIP/WebRTC/Chat
50+
Contact sales
✅ Real calls
❌
Roark
$2M
Phone/WebSocket/Replay
40+
$500/mo
✅ Real calls
SDKs only
Coval
$3.8M
Text + Audio sim
~15 documented
$300/mo
✅ Synthetic
❌
Cekura
$2.9M
Real phone calls
10+ auto, custom
$30/mo
✅ Real calls
Skills only
Bluejay
$4M
Digital Humans (500+ vars)
Latency/accuracy/etc
Contact sales
✅ Synthetic
❌
Maxim
$3M
HTTP endpoint / trace
LLM eval suite
Free tier
❌ Observability only
Minimal
Braintrust
$80M
Dataset → Task → Scorer
25+ AutoEvals
Free tier
❌ Via Evalion
autoevals (807⭐)
Evalion
Undisclosed
Hybrid AI + Human
Binary + CSAT
Contact sales
✅ Full audio
❌
Sipfront
€1.8M
SIP/RTP/PSTN native
MOS/jitter/PDD/etc
Contact sales
✅ Telephony native
baresip fork
Leaping
$4.7M
Built-in only
CSAT/faithfulness
Per-minute
❌ Own platform only
❌
Retell Assure
N/A
Post-deploy monitoring
Latency/halluc/sentiment
Free 100min
❌ Text sim only
❌
Vapi Evals
N/A
Mock conversation JSON
Pass/fail per judge
Per-minute call cost
❌ Text only via API
❌
LiveKit Test
N/A
pytest assertions
Behavioral/tool calls
Free (OSS)
❌ Text only
✅ Apache-2.0
voice-lab
N/A
LLM-as-judge
Custom JSON metrics
Free (OSS)
❌ Text only
✅ Apache-2.0


AREA 2: Voice agent platform testability
What every major platform exposes for external testing
The critical insight for building an open-source testing framework is understanding exactly what hooks each voice platform provides. Vapi has the richest testability surface, followed by Retell and LiveKit. Bland offers unique node-level regression testing. ElevenLabs provides the strongest managed simulation API.
Vapi — richest API surface for testing
Base URL: https://api.vapi.ai, Bearer token auth.
Key endpoints for testing:
POST /call — Create outbound call (PSTN, SIP, or WebSocket transport)
POST /eval/run — Execute programmatic evals with mock conversations
GET /eval/run/{id} — Poll for eval completion
POST /analytics — Custom metric queries
WebSocket transport: Create call with WebSocket type → bidirectional real-time audio streaming in PCM (pcm_s16le) or Mu-Law (mulaw). Returns listenUrl (audio monitoring) and controlUrl (call control: say, add-message, inject-context, end-call, transfer).
Webhook events (15+ types): assistant-request, tool-calls, status-update, end-of-call-report (complete summary with transcript, recording, analysis), transcript (partial/final with turnId), speech-update, user-interrupted, language-change-detected, call.endpointing.request.
SIP: Full SIP trunking with custom headers. PSTN: Twilio, Telnyx, Vonage providers.
SDKs: Web (@vapi-ai/web), Python (vapi-server-python), Node (@vapi-ai/server-sdk), CLI.
Known testing pain points: Latency stacking (6–7s delays when external APIs lag), voice quality degradation under load ("robotic"), max 50 test cases per suite, complex pricing ($0.05/min orchestration + provider costs = ~$0.20–0.30/min effective).
Retell AI — uniquely transparent debug logs
Auth: API key in Authorization header. Webhook signature via X-Retell-Signature.
Key testing hooks:
createPhoneCall({from_number, to_number, agent_id}) — Outbound calls
registerPhoneCall() — SIP dial-to flows returning call_id and SIP URI
Batch Simulation Testing API — Define test cases with user prompts, run in bulk, import/export as JSON
public_log_url — Full debug log with all LLM WebSocket requests/responses and per-turn latency tracking
recording_multi_channel_url — Separate audio channels per party (critical for audio analysis)
Custom LLM WebSocket protocol: Your server exposes wss://your-domain/llm-websocket/:call_id. Retell connects and sends {response_id, transcript: [{role, content}], interaction_type: "update_only"|"response_required"|"reminder_required"}. You stream responses with {content, content_complete: false/true}.
Call object fields include: transcript_object (word-level with timestamps), transcript_with_tool_calls, call_analysis (sentiment, success, summary, custom data), latency (structured tracking), llm_token_usage, disconnection_reason (detailed codes), kb_retrieved_contents.
Known pain points: 700–800ms typical latency, webhook timeout at 5 seconds (40% failure on mobile networks), STT garbling during simultaneous speech, partial transcript race conditions causing duplicate API calls.
LiveKit Agents — most instrumented open-source framework
Architecture: Agent registers via authenticated WebSocket, boots job subprocess joining LiveKit room as WebRTC participant. STT → LLM → TTS pipeline with pluggable providers.
APIs: WebRTC (primary), SIP bridge via Twirp HTTP POST (https://<domain>/twirp/livekit.SIP/<Method>), REST for room/participant/agent dispatch management.
SIP API endpoints: CreateSIPInboundTrunk, CreateSIPOutboundTrunk, CreateSIPDispatchRule, CreateSIPParticipant, TransferSIPParticipant — all with signed JWT auth.
Internal metrics (emitted via metrics_collected event): LLMMetrics (TTFT, tokens/sec), STTMetrics (audio vs. request duration), TTSMetrics (TTFB, audio duration, char count), VADMetrics (idle time, inference duration), EOUMetrics (end-of-utterance delay, transcription delay), InterruptionMetrics (detection latency). Prometheus HTTP server on port 8081. Native OpenTelemetry with Langfuse/SigNoz/LangSmith integrations.
Total conversation latency ≈ EOUMetrics delay + LLM TTFT + TTS TTFB.
Community pain points: False-positive interruptions (most common complaint), turn detection tuning, LLM latency spikes difficult to isolate, get_job_context() inaccessible in test environments.
Pipecat — most architecturally flexible
GitHub: ~5,000+ stars, BSD-2-Clause. Pipeline-based: Frames → Frame Processors → Pipelines → Transports.
Testability hooks: Can bypass audio entirely and inject TranscriptionFrame directly into pipeline for text-based testing. Observers monitor frame flow without modifying pipeline. Frame filters (reached_upstream_types, reached_downstream_types) for inspecting frame flow. Built-in metrics: TTFB tracking, processing time per processor, usage tracking. OpenTelemetry integration with hierarchical traces (Conversation → Turns → Service calls).
Transports: Daily WebRTC (primary), LiveKit WebRTC, SmallWebRTCTransport, FastAPI WebSocket, Local (audio I/O testing).
28+ TTS providers, 15+ LLM providers, 15+ STT providers — the broadest integration ecosystem.
No native test framework — relies on building blocks and third-party tools (Coval, Bluejay, Cekura, Hamming all have documented Pipecat integrations).
ElevenLabs Conversational AI — strongest managed simulation
WebSocket API: wss://api.elevenlabs.io/v1/convai/conversation?agent_id={agent_id}. Client sends user_audio_chunk (base64 PCM 16kHz 16-bit), receives vad_score (0–1), user_transcript, agent_response, audio chunks, interruption events, ping/pong for latency.
Simulation API (unique): POST /v1/convai/agents/{agent_id}/simulate — full conversation simulation with configurable user prompt, tool mock configs, partial conversation history for mid-conversation unit testing, maxTurns/timeout controls. Streaming variant at /simulate/stream.
Testing framework: Scenario testing (LLM evaluation against success criteria) + tool call testing (exact match/regex/LLM eval for parameters). Batch testing with CI/CD CLI integration.
Monitoring WebSocket (Enterprise): wss://api.elevenlabs.io/v1/convai/conversation/{conversation_id}/monitor — live observation with control commands (terminate, transfer, human takeover, inject context).
Bland AI — unique node-level regression testing
Base URL: https://api.bland.ai/v1/, API key in authorization header (not Bearer).
Unique feature: POST /v1/node_test_invoke — invoke tests on specific pathway nodes. Generates 5+ variants of user messages with different communication styles, LLM-grades each, shows extracted variables, route choices, and loop condition evaluations. GET /v1/node_test_run retrieves results.
Other hooks: POST /v1/calls/{id}/analyze (AI analysis), POST /v1/intelligence/emotions (emotion from audio up to 25MB), GET /v1/calls/{id}/event-stream (SSE real-time monitoring), GET /v1/calls/{id}/correct (corrected transcripts with confidence scores and speaker diarization).
Twilio — deepest telephony metrics
ConversationRelay WebSocket protocol: Twilio sends {type: "prompt", voicePrompt: "..."} and {type: "interrupt", utteranceUntilInterrupt: "..."}. Your app responds with {type: "text", token: "Hello", last: false/true}.
Voice Insights API (GET https://insights.twilio.com/v1/Voice/{CallSid}/Metrics): Jitter (inbound/outbound), packet loss, packet rate, MOS, round trip time, audio levels — sampled every 10 seconds. Available ~90 seconds after call completion.
Latency benchmarks: ConversationRelay p50 491ms, p95 713ms.
Deepgram, AssemblyAI, and Cartesia — component-level testing
Deepgram Voice Agent API: wss://api.deepgram.com/v1/agent/converse — unified STT+LLM+TTS in single WebSocket at $4.50/hr. Settings message configures all three components. Events include UserStartedSpeaking (barge-in), AgentThinking, ConversationText, AgentAudioDone. Word-level confidence scores in STT results.
AssemblyAI Universal-Streaming: wss://streaming.assemblyai.com/v3/ws — immutable turn-based transcription (no overwriting). end_of_turn_confidence (0–1), word-level confidence/timestamps, configurable end_of_turn_confidence_threshold and silence thresholds. ~150ms P50 latency. $0.15/hr. Up to 1,000 real-time keyterms for domain-specific accuracy.
Cartesia TTS: wss://api.cartesia.ai/tts/websocket — 90ms time-to-first-audio, step_time field per chunk for latency measurement, word and phoneme timestamps, 60+ emotion controls, context-based multiplexing for interruption handling. Model snapshot pinning (sonic-3-2026-01-12) for reproducible testing. $0.13/hr.

AREA 3: The complete voice agent metric taxonomy
Audio and speech quality metrics every framework needs
WER (Word Error Rate) — the foundational ASR metric:
WER = (Substitutions + Deletions + Insertions) / Total Reference Words × 100%

Range: 0% (perfect) to 100%+. Benchmarks: <5% clean audio, <10% noisy for production voice agents. Variants include CER (character-level, preferred for logographic languages), SER (sentence-level), and LASER (LLM-based severity-weighted scoring). Tools: jiwer (Python), HuggingFace evaluate.
MOS (Mean Opinion Score) — ITU-T P.800: Scale 1–5. Automated prediction via DNSMOS (Microsoft, no-reference, outputs SIG/BAK/OVRL on 1–5 scale, open-source ONNX models), UTMOS/UTMOSv2 (state-of-the-art naturalness prediction), ViSQOL (Google, open-source Apache-2.0, full-reference, designed for VoIP). Voice agent TTS target: MOS >4.3 (good), 3.8–4.3 (warning), <3.8 (critical).
PESQ (ITU-T P.862) — officially deleted by ITU-T in January 2024, superseded by P.863. Full-reference, scoring -0.5 to 4.5 raw, mapped to MOS-LQO 1.0–4.5. MOS mapping: MOS-LQO = 0.999 + 4.999/(1 + exp(-1.4945 × PESQ + 4.6607)). Still in many codebases but should be considered deprecated.
POLQA (ITU-T P.863) — the current gold standard for perceptual voice quality. Supports NB/WB/SWB/fullband up to 48 kHz. Handles time-varying delays and HD Voice. RMSE of 0.14 (NB) vs. PESQ's 0.19. Commercial-only licensing from OPTICOM — a significant cost barrier for open-source frameworks.
STOI (Short-Time Objective Intelligibility): Range 0–1. Computes correlation between clean and degraded signals in short-time TF regions. >0.9 = highly intelligible, <0.6 = poor. Implementation: pystoi, torchmetrics.audio.stoi.
SNR/SNRI: SNR(dB) = 10 × log₁₀(P_signal / P_noise). Segmental SNR (frame-level average) better correlates with subjective tests. 30+ dB = clean, 20 dB = barely noticeable noise, 0 dB = equal energy.
Speaker similarity (for voice cloning): Cosine similarity of ECAPA-TDNN embeddings. >0.85 = excellent, 0.75–0.85 = good, <0.6 = poor. Subjective SMOS ≥4.0 = strong cloning.
Latency metrics with precise measurement methodology
Component-level latency budget for a voice agent pipeline:
Component
Typical Range
Dominance
End-of-speech detection
~200ms
Framework-dependent
STT (streaming final)
100–400ms
Provider-dependent
LLM TTFT
200–800ms
Dominates 70%+ of total
TTS TTFB
50–300ms
Critical for perceived speed
Network/transport
50–200ms
Geography-dependent
Orchestration overhead
20–100ms
Framework-dependent

Percentile targets for production voice agents:
Percentile
Target
Current Reality (Hamming, 4M+ calls)
P50
<800ms
1.4–1.7s
P95
<1,500ms
4.3–5.4s
P99
<3,000ms
8.4–15.3s

Human perception thresholds: <300ms perceived as instantaneous; >500ms users wonder if heard; >1,000ms assumed connection failure; >1,500ms triggers neurological stress response.
Jitter: <20ms good, 20–30ms acceptable, >30ms poor (choppy audio). Packet loss: <1% good, 1–5% audible gaps, >5% call breakdown. ITU-T G.114 mandates max 150ms one-way latency.
E-Model MOS derivation (ITU-T G.107):
Effective_Latency = Latency + 2 × Jitter + 10
If Effective_Latency < 160: R = 93.2 - (Effective_Latency / 40)
If Effective_Latency >= 160: R = 93.2 - (Effective_Latency - 120) / 10
R = R - 2.5 × Packet_Loss(%)

Conversation quality metrics
Task Completion Rate: TCR = Completed Tasks / Total Attempts × 100. Best measured via deterministic backend state checks (was the appointment actually booked?), not LLM judgment. Benchmarks: appointment scheduling >90%, order tracking 85–95%, general customer service 75–80%.
Turn Efficiency: Optimal Turns / Actual Turns. Establish golden-path conversations per task type. Flag conversations exceeding 2× optimal.
Context Retention: Correctly Retained References / Total Cross-Turn References × 100. Test by providing information at turn M, then referencing it at turn N. Measure at increasing distances (1, 3, 5 turns back).
Repetition Rate: Repeated Utterances / Total Agent Utterances × 100. Detect via embedding cosine similarity (threshold >0.85 flags repetition). Hamming scoring: 100 (no repetitions), 50 (repeated twice), 0 (repeated 3+ times).
Hallucination Rate: Responses with Hallucinations / Total Responses × 100. Verify each factual claim against knowledge base, tool results, and conversation context. Targets: healthcare <0.5%, financial <1%, general <1%.
Intent Recognition Accuracy: Correctly Classified Intents / Total Utterances × 100. Report precision/recall/F1 per intent class. Benchmark: >95% good, 90–95% warning, <90% critical.
Slot Filling: SER = (Inserted + Deleted + Substituted Slots) / Total Reference Slots × 100. Voice-specific: dates, phone numbers, and alphanumeric codes are highest error categories.
Interruption and turn-taking metrics
Barge-in detection time: T(agent_audio_stop) - T(user_speech_onset). Target <200ms. Sub-100ms VAD detection is standard expectation.
False positive interruption rate: Non-intentional sounds (backchannels "uh-huh", coughs, echo) incorrectly classified as barge-in. LiveKit's adaptive interruption uses a CNN-based model that detects true barge-ins faster than VAD in 64% of cases.
Context recovery after interruption: Does agent address the new input AND retain pre-interruption context? Target >90% recovery rate.
Response gap: Silence between user turn end and agent turn start. Target 200–500ms; >800ms feels broken.
Robustness across real-world conditions
Noise robustness scoring: 1 - (WER_noisy - WER_clean) / WER_clean. Test at SNR levels: clean (∞), 20dB (+0–2% WER), 10dB (+5–10%), 3dB (critical tipping point), 0dB (+15–20%). Speech Robust Bench (ICLR 2025) defines 114 perturbation types.
Accent equity gap: max(WER_accent_group) - min(WER_accent_group). Target gap <5%. Research shows commercial ASR WER for African American Vernacular English nearly double that of white speakers (Koenecke et al. 2020).
Speech speed: Test 0.5×–2.0× normal rate via time-stretching. Critical for elderly (slower) and urgent (faster) callers.
Compliance metrics with zero tolerance
PII detection: Precision and Recall against known PII injection. Automated detection achieves 93–95% accuracy (Hamming). Both caller and agent audio must be redacted. Latency cost: 10–50ms for real-time detection.
HIPAA: Agent must verify identity BEFORE disclosing PHI. Common failure: asking for symptoms before confirming identity.
PCI-DSS: Card numbers/CVV must never be echoed back. Target violation rate: 0%. Penalties up to $100K/month.
AI disclosure: Agent must identify as AI within first 10 seconds (jurisdictional requirement). Measure word-level accuracy of required disclosure scripts.
Tool calling accuracy
Tool correctness (DeepEval): Correctly Used Tools / Total Tools Called. Berkeley BFCL sub-metrics: AST accuracy, executable accuracy, relevance detection (correctly withholding calls when inappropriate).
Parameter extraction accuracy: Correct Parameters / Total Parameters × 100. Voice-specific cascading risk: "Flight 1850" misheard as "Flight 1815" passes structural checks but books wrong flight.
Graceful degradation rate: Properly Handled Tool Failures / Total Failures × 100. Test: API timeout, unexpected data, partial failure, network interruption mid-call.
Tool call latency impact: Total turn latency including tool calls should remain under 1,500ms at P95. Track via OpenTelemetry spans per tool call.
LLM-as-judge calibration methodology
All semantic evaluation in current platforms relies on LLM-as-judge. Best practices for implementation:
Calibrate against 50–100 human-annotated examples. Target >80% agreement (comparable to inter-annotator agreement).
Use Chain-of-Thought prompting (G-Eval approach): Judge generates evaluation steps from criteria before scoring.
Prefer binary over fine-grained: LLMs are more reliable at pass/fail than 1–10 scales.
Known biases: Position bias (prefers first output in pairwise comparison), verbosity bias (prefers longer text), self-enhancement bias (rates own outputs higher).
Cost: ~$0.01–0.10 per assessment. 1,000 responses evaluated in minutes vs. days for humans.
EVA framework (ServiceNow/HuggingFace, March 2026): Selects different judge models per metric based on which performs best on curated evaluation datasets.

Conclusion: where the open-source opportunity lies
Three structural gaps make this market vulnerable to disruption. First, no platform covers the full stack: Sipfront handles SIP/RTP but not conversation semantics; Hamming/Cekura handle conversations but not protocol-level testing; all skip true audio pipeline evaluation in favor of text-only shortcuts. An open-source framework that instruments the complete path — from SIP INVITE through RTP media to STT→LLM→TTS latency to conversation-level scoring — would be genuinely differentiated.
Second, every closed platform's evaluation is a black box. Hamming claims 95–96% human agreement but doesn't publish methodology. Evalion publishes a benchmark paper but authored it themselves. An open-source framework with transparent, reproducible scoring — combining deterministic metrics (WER, latency percentiles, PESQ/ViSQOL), heuristic audio analysis (barge-in timing, gibberish detection, pitch analysis à la Cekura's three-layer approach), and calibrated LLM-as-judge with published agreement rates — would earn developer trust.
Third, the testability surface is already exposed. Vapi's Evals API, Retell's public debug logs, LiveKit's Prometheus metrics, Pipecat's frame injection, ElevenLabs' simulation API, Deepgram's Voice Agent WebSocket, AssemblyAI's turn-based streaming, and Cartesia's step-time instrumentation collectively provide every hook needed. The recommended implementation stack: ViSQOL (Apache-2.0) for perceptual quality, DNSMOS (open-source ONNX) for no-reference monitoring, jiwer for WER, ECAPA-TDNN for speaker similarity, OpenTelemetry for pipeline tracing, and pytest with LiveKit-style fluent assertions for behavioral testing. Start with task completion, WER, turn latency (P50/P95/P99), and hallucination rate — these four metrics cover 80% of production quality issues — then expand into robustness, compliance, and telephony-layer testing.

