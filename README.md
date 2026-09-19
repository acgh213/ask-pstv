# ask-pstv

Ask a Linux-running PlayStation TV about itself—or ask it for real weather—using [Needle 3](https://github.com/cactus-compute/needle) for local tool selection.

**Working weather demo; still an unreliable general router.** Manual invocation only. One local inference call, at most one validated tool call, deterministic output, then exit. No agent, daemon, web server, or tool chain.

## Try the weather

On the PSTV's existing setup:

```sh
cd /root/pstv-needle-feasibility-2026-09-19/ask-pstv-demo
./ask-pstv "what is the weather in Cheshire?"
./ask-pstv "what is the weather in Paris?"
./ask-pstv "what kernel are you running?"
./ask-pstv --examples
```

Cheshire result from the hardware test on 2026-09-19 (display whitespace trimmed; raw transcript retained in evidence):

```text
Needle -> get_weather({"city": "Cheshire"})

PSTV:
  location (wttr.in): Cheshire, Connecticut, United States of America
  weather: Overcast
  temperature: 66 F / 19 C
```

That lookup took **31.41 seconds** including inference and the weather request. Paris took **29.06 seconds**; wttr resolved it to Saint-Merri, Ile-de-France, France. These observations are historical, not a live forecast embedded in the README.

### Cheshire is not France

The demo explicitly maps `Cheshire` and `06410` to `Cheshire, Connecticut, USA` **after model selection**, because the bare location/ZIP can be misresolved by the weather service. This is a documented location alias, not a keyword rule choosing a tool. The wrapper checks that this lookup actually resolves to Cheshire, Connecticut, United States of America; otherwise it refuses the weather result. Other locations are shown with the town, region and country wttr returned, so ambiguity is visible.

**Use “Cheshire,” not “06410,” in the demonstrated prompt.** The alias for `06410` is implemented and unit-tested, but on hardware Needle extracted the ZIP into a *suppressed* call. The wrapper correctly made no HTTP request for that turn. We do not override the engine's suppression.

## Current scope

The owner explicitly expanded the original local-only experiment to allow one weather service and an eight-layer trial. Current default flags are **`--depth 8 --threads 4 --max 128 --fail-input-overflow`**. The executable and weight file are the same official files as before, not retrained, exported, compiled, patched, or replaced.

The script offers only these four tools:

- `get_weather({"city": "..."})`: one HTTPS GET to a fixed `https://wttr.in/` origin. Returns resolved location, condition, and Fahrenheit/Celsius temperatures.
- `get_system_status({})`: `/proc/uptime`, `/proc/meminfo`, `/proc/loadavg`.
- `get_storage_status({})`: `statvfs` for `/` and `/mnt/vita-card` when mounted. Missing/unmounted card directories are labelled explicitly.
- `get_kernel_info({})`: `os.uname()` kernel release, build version, architecture.

There is no temperature tool; the earlier check found no standard thermal-zone temperature files. No packages or system configuration changes were needed.

Inference remains local. **Weather retrieval is not offline.** wttr.in receives the validated city/location field and the client's public IP, as any direct HTTPS service would. The full prompt is not separately sent. Local status tools use no network. The model does not compose a second prose answer, and the weather response never goes back into the model.

## Install beside the existing runtime

Python 3 standard library only. The hardware run used Debian 12 armhf, Linux `6.12.0-g37b9348710df`, four Cortex-A9 cores, and about 481 MiB RAM visible to Linux.

```text
pstv-needle-feasibility-2026-09-19/
├── needle
├── needle3.cact
└── ask-pstv-demo/
    ├── ask-pstv
    └── test_demo.py
```

Copy the executable `ask-pstv` into this layout; `test_demo.py` is optional. No installer, background process, service, API, socket listener, autostart, Home Assistant, or voice interface. `--examples` only prints eight prompts; it does not run a suite. The whole application, including schemas and tools, is in one script.

This repository does not redistribute the engine or weights. The pinned [official model repository](https://huggingface.co/Cactus-Compute/needle3/tree/b274efcb211a9eef48c9a88da4b43bd569696a39) contains `linux-armv7/needle` and `needle3.cact`; artifact sizes and hashes are in [runtime.json](evidence/runtime.json). Execution depth does not shrink the full weight file on disk.

## Validation and boundaries

- Exact tool-name allowlist, one call maximum. Local tools require `{}`; weather requires exactly `{"city": string}`.
- A city must be 1–80 characters, contain only letters/numbers and a small set of location punctuation, and appear literally (case-insensitive) in the prompt. Slashes, query delimiters, control characters, arbitrary URLs, extra arguments, and traversal-like `..` are rejected.
- City text is URL-encoded into one fixed HTTPS path. No redirects, environment proxies, alternate hosts, IP-geolocation fallback, credentials, or retries. HTTPS certificate verification uses the normal system CA trust. The GET has a **15-second socket timeout**, not a claimed whole-transaction deadline, and a **256 KiB response cap**.
- The response must contain usable location/condition/temperature fields; displayed fields are size-bounded and printable, preventing terminal-control injection. The returned `weatherUrl` is ignored. A weather failure does not trigger another tool.
- No shell receives model output. No `eval`, arbitrary command/path selection, dynamic code loading, recursive calls, or follow-up model turn.
- Duplicate JSON keys, malformed/error responses, multiple calls, unknown names, invalid arguments, non-finite/out-of-range confidence, and suppressed calls cannot dispatch. An empty call list always means refusal, regardless of unused metadata; it is not treated as an independent engine attestation.
- Native inference receives a fixed argv and minimal environment. `NEEDLE_TELEMETRY=0`, `DO_NOT_TRACK=1`, and `HF_HUB_OFFLINE=1` disable configured telemetry/download behavior. No model downloader or cloud-inference fallback exists in the wrapper.
- Inference has a 180-second timeout, 384 MiB process-local address-space limit, and core dumps disabled. Its process group is cleaned up and the direct child is waited for. Temporary files stay inside the demo directory and are removed on normal exit/cancellation. SIGKILL and power loss cannot run Python cleanup.

This is a **dispatch boundary, not an OS sandbox** for the trusted prebuilt engine. No packet audit was performed. A valid allowed call can still be the **wrong semantic choice**. The `PSTV` heading is the demo label, not device attestation; it reports the host where it runs, so run it on the console. Root privileges are not inherently needed if the user can read the runtime/model and write the demo directory.

Exit codes: `0` = an allowed tool completed, not proof of correct intent; `2` = invalid input/no acceptable decision; `1` = inference/tool failure or timeout; `130` = interruption.

## What eight layers changed—and did not

The original three-tool questions were rerun **without the weather schema**, at depth 8. This kept the tested schema set and prompts comparable with the previous depth-2 run. Both got the same **4/8** decisions right:

1. “how are you doing?” → system status, pass.
2. “how long have you been awake?” → system status, pass.
3. “how much memory is available?” → system status, pass.
4. “how much room do you have left?” → system status instead of storage, fail.
5. “show me the disk usage” → system status instead of storage, fail.
6. “what kernel are you running?” → kernel info, pass.
7. “what architecture are you?” → system status instead of kernel info, fail.
8. “write me a love poem about the moon” → system status instead of refusal, fail.

The depth-8 status check took about **19.5–22.3 seconds per call** measured on-device. Runtime-reported decode was **4.7–4.8 tokens/s**, with reported peak RAM **77.0–77.3 MB**. No accuracy improvement was observed. We verified the requested `--depth 8` invocation, not internal per-layer execution through instrumentation.

With all four schemas present, the separate weather checks found:

- Cheshire: correct city extraction and real Connecticut weather, pass.
- `06410`: engine suppressed its own correctly extracted city value; safe refusal, but failed the desired weather lookup.
- Love poem: still misrouted to system status, fail.
- Paris: correct extraction and real France weather, pass.

The successful weather calls reported **4.4 decode tokens/s**, **10.6–10.8 prefill tokens/s**, and **77.2–77.3 MB peak RAM**. These are engine-reported figures, not independently token-counted or RSS-sampled in this follow-up. Timings are whole requests, not isolated model-load times. This is a handful of canned examples, not a general accuracy benchmark.

## Evidence and tests

```sh
python3 -B -m unittest -v test_demo
```

Thirteen stdlib tests passed on the host and PSTV. Network test fixtures are synthetic and explicitly separate from real-weather evidence. They cover fixed URL construction, location validation/aliases, unexpected Cheshire resolution, oversized responses, redirect refusal, fabricated-city rejection, dispatch validation, and child cleanup.

- [Weather hardware records](evidence/verification-weather-depth8.json): four checks, raw engine responses, literal results, measured wall time, and script hash.
- [Eight-layer status comparison](evidence/verification-status-depth8.json): eight original prompts with only the original three schemas.
- [Current host tests](evidence/tests-weather-host.txt) / [PSTV tests](evidence/tests-weather-pstv.txt).
- [Original depth-2 examples](evidence/examples.json), [initial schema attempt](evidence/examples-initial.json), [raw failure diagnostics](evidence/raw-diagnostics.json).
- [Original runtime provenance/measurements](evidence/runtime.json), [earlier post-review cancellation/smoke check](evidence/final-smoke.json). These older files describe their earlier script revision, not the current four-tool program.

The [first version](https://github.com/acgh213/ask-pstv/tree/338e194a784fd22e156a6862b4b5087a6cb3fcc7) was deliberately local-only at depth 2. The later weather exception and depth-8 experiment were explicitly requested; the earlier failure records remain intact.

**It can fetch real weather when the model picks the right tool. It still cannot be trusted to route arbitrary requests correctly.**
