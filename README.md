# ask-pstv

Ask a Linux-running PlayStation TV about itself, get real weather, pull up a Pokédex card, or roll real dice, using [Needle 3](https://github.com/cactus-compute/needle) for local tool selection.

**Working weather, Pokédex and dice demos; still an unreliable general router.** Manual invocation only. One local inference call, at most one validated tool call, deterministic output, then exit. No agent, daemon, web server, or tool chain.

## A dice goblin

```sh
./ask-pstv "roll three twenty-sided dice"
./ask-pstv "roll four six-sided dice"
```

Recorded on the PSTV:

```text
Needle -> roll_dice({"count": 3, "sides": 20})

PSTV:
  rolled 3d20
  rolls: 7, 17, 13
  total: 37
```

The model supplies `count` and `sides`. `secrets.randbelow` produces the faces locally, and the model never sees or invents a result. Two identical prompts rolled `7, 17, 13` and `15, 4, 14`, which is the whole point: real randomness, not a language model guessing dice.

Spelled-out numbers work: `three twenty-sided` and `four six-sided` both produced exactly the requested roll. **Dice notation does not.** Asked for `2d6` she answered `count 2, sides 2`; `4d6` became `count 4, sides 2` ("sides defaults to 2"); `d20` came back as `count 20, sides 2`. Raw responses are in the probe evidence below.

The wrapper turns those misreads into refusals instead of wrong rolls:

- Every number must appear in the request as digits or as an English word. `roll thirteen ten-sided dice` (read as `3`) and `roll 4d6` (sides 2) are refused rather than rolled.
- If the request contains dice notation, the chosen roll must match it. `roll 2d6` — where one digit grounds both fields — is refused rather than rolled as 2d2.
- `roll some dice` states no numbers. She proposed `count 3, sides 3`, and the engine's own grounding check suppressed it; the wrapper also refuses.

Accepted range is **1–20 dice, 2–100 sides**. No modifiers, exploding dice, keep-highest, or advantage. **Notation is effectively unsupported — say the numbers.** All six dice checks passed; each call took **50.3–53.9 seconds**.

## A Pokédex in a PlayStation

```sh
./ask-pstv "tell me about Gengar"
./ask-pstv "what types and abilities does Pikachu have?"
./ask-pstv "look up Mr. Mime in the Pokedex"
```

All three routed and returned real API-backed cards on the PSTV. A recorded cached lookup:

```text
Needle -> get_pokemon_info({"name": "Gengar"})

PSTV:
  POKEDEX | GENGAR [PokeAPI #94]
  types: Ghost / Poison
  abilities: Cursed Body
  base stats: HP 60 | Atk 65 | Def 60
              SpA 130 | SpD 75 | Spe 110
  source: PokeAPI (cached)
```

The model supplies only the name. Types, abilities (including hidden abilities), and all six base stats come from [PokeAPI](https://pokeapi.co/docs/v2), then ordinary Python formats the card. These are current API values, **not generation-specific game data**, battle stats, or model-generated strategy. The displayed ID is the PokeAPI Pokémon resource ID; alternate forms may not share the species' National Dex number.

The three complete card requests took **38.18–39.95 seconds** in this run. A fake name, `Definitelynotapokemon`, produced a clean lookup failure, not fabricated facts. Weather in Cheshire still worked with all five schemas available (56.32 seconds in that single regression check). These samples do not establish general routing accuracy.

### Local cache, not a downloader

PokeAPI's [fair-use policy](https://pokeapi.co/docs/v2#fairuse) requests local caching. The first successful lookup makes one HTTPS GET to `https://pokeapi.co/api/v2/pokemon/<validated-name>/`; following lookups use `.pokemon-cache/<name>.json` inside the demo directory. Only the small fields needed for the card are retained. The three actual cached records were **991, 1,020, and 1,223 bytes**. No images, movesets, other URLs in API responses, or extra resources are fetched.

A cached Gengar lookup was also verified with the network-fetch function replaced by a function that raises on any call. The card still rendered. This checks the tool's cache behavior, not an OS-wide network audit of the native model runtime. The cache has no automatic expiry; remove an individual record manually to refresh it. A damaged/mismatched cache record fails closed without an automatic HTTP retry.

Names must be mentioned literally in the prompt, then pass a narrow ASCII slug validator. Conventional spellings `Mr. Mime`/`Mr Mime`, `Farfetch'd`, `Mime Jr.`, and the two Nidoran gender symbols have explicit aliases. Only Gengar, Pikachu and Mr. Mime were hardware-tested in this step. Arbitrary names, numbers, punctuation variants and forms are not promised to work. Numeric Pokédex lookup is not implemented.

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

In the earlier four-tool version, that lookup took **31.41 seconds** including inference and the weather request. Paris took **29.06 seconds**; wttr resolved it to Saint-Merri, Ile-de-France, France. These observations are historical, not a live forecast embedded in the README.

### Cheshire is not France

The demo explicitly maps `Cheshire` and `06410` to `Cheshire, Connecticut, USA` **after model selection**, because the bare location/ZIP can be misresolved by the weather service. This is a documented location alias, not a keyword rule choosing a tool. The wrapper checks that this lookup actually resolves to Cheshire, Connecticut, United States of America; otherwise it refuses the weather result. Other locations are shown with the town, region and country wttr returned, so ambiguity is visible.

**Use “Cheshire,” not “06410,” in the demonstrated prompt.** The alias for `06410` is implemented and unit-tested, but on hardware Needle extracted the ZIP into a *suppressed* call. The wrapper correctly made no HTTP request for that turn. We do not override the engine's suppression.

## Current scope

The owner explicitly expanded the original local-only experiment to allow one weather service and an eight-layer trial. Current default flags are **`--depth 8 --threads 4 --max 128 --fail-input-overflow`**. The executable and weight file are the same official files as before, not retrained, exported, compiled, patched, or replaced.

The script offers only these six tools:

- `roll_dice({"count": N, "sides": M})`: real local randomness from `secrets` on validated integer arguments; the model never supplies a face value.
- `get_pokemon_info({"name": "..."})`: one fixed PokeAPI lookup on a cache miss; deterministic types, abilities and base-stat card.
- `get_weather({"city": "..."})`: one HTTPS GET to a fixed `https://wttr.in/` origin. Returns resolved location, condition, and Fahrenheit/Celsius temperatures.
- `get_system_status({})`: `/proc/uptime`, `/proc/meminfo`, `/proc/loadavg`.
- `get_storage_status({})`: `statvfs` for `/` and `/mnt/vita-card` when mounted. Missing/unmounted card directories are labelled explicitly.
- `get_kernel_info({})`: `os.uname()` kernel release, build version, architecture.

There is no temperature tool; the earlier check found no standard thermal-zone temperature files. No packages or system configuration changes were needed.

Inference remains local. **Uncached API lookups are not offline.** wttr.in receives the city/location field; PokeAPI receives the Pokémon-name slug on a cache miss. Each service also sees the client's public IP, as any direct HTTPS service would. The full prompt is not separately sent. Local status tools use no network. The model does not compose a second prose answer, and API responses never go back into the model.

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

Copy the executable `ask-pstv` into this layout; `test_demo.py` is optional. No installer, background process, service, API, socket listener, autostart, Home Assistant, or voice interface. `--examples` only prints nine prompts; it does not run a suite. The whole application, including schemas and tools, is in one script.

This repository does not redistribute the engine or weights. The pinned [official model repository](https://huggingface.co/Cactus-Compute/needle3/tree/b274efcb211a9eef48c9a88da4b43bd569696a39) contains `linux-armv7/needle` and `needle3.cact`; artifact sizes and hashes are in [runtime.json](evidence/runtime.json). Execution depth does not shrink the full weight file on disk.

## Validation and boundaries

- Exact tool-name allowlist, one call maximum. Local tools require `{}`; weather requires exactly `{"city": string}`; Pokédex exactly `{"name": string}`; dice exactly `{"count": int, "sides": int}`. Booleans, floats, numeric strings, negative values and out-of-range values are rejected by type and bounds, not coerced.
- Every argument must appear in the request: strings literally (case-insensitive), numbers as digits or an English number word. Dice notation typed by the user must match the roll that was chosen.
- A city must be 1–80 characters, contain only letters/numbers and a small set of location punctuation, and appear literally (case-insensitive) in the prompt. Slashes, query delimiters, control characters, arbitrary URLs, extra arguments, and traversal-like `..` are rejected.
- City text is URL-encoded into one fixed HTTPS path. No redirects, environment proxies, alternate hosts, IP-geolocation fallback, credentials, or retries. HTTPS certificate verification uses the normal system CA trust. The GET has a **15-second socket timeout**, not a claimed whole-transaction deadline, and a **256 KiB response cap**.
- Pokémon names are capped at 60 characters and mapped to lowercase ASCII slugs, with only explicit spelling aliases. The fixed PokeAPI endpoint shares the redirect/proxy/TLS/timeout protections; its response/cache cap is **1 MiB**. Returned identity, field shapes, printable safe names, and bounded integer stats are validated before display/cache writes. The model cannot choose a cache path or API URL.
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

## What a decision costs

One prompt, the official binary, measured on the PSTV ([raw evidence](evidence/scale-probe.json)):

- **1 tool**, depth 8, max 128, 4 threads: **13.1 s** — 237 B of schema, 5.2 decode t/s, 77.3 MB
- **3 tools**, same flags: **21.2 s** — 743 B, 4.8 decode t/s, 77.2 MB
- **6 tools**, same flags: **52.9 s** — 1943 B, 3.6 decode t/s, 77.2 MB
- 6 tools, **max 8** instead of 128: **40.7 s** — capping the prose tail saves 12.2 s
- 6 tools, **depth 2** instead of 8: **52.5 s** — depth costs nothing and buys nothing
- 6 tools, **2 threads** instead of 4: **90.5 s** — keep `--threads 4`

Tool count is the price, and it climbs steadily: **+8.1 s from 1 tool to 3**, then **+31.7 s from 3 tools to 6** — roughly ten seconds for every tool added above three. The same slope appears in this evening's CLI runs: 3 tools ≈ 21 s, 4 ≈ 30 s, 5 ≈ 39 s, 6 ≈ 52 s.

Cactus's tool-design guide states that *five or fewer tools render directly; above that, retrieval engages — every schema is embedded, the request is embedded, only the five closest tools enter the context, and an unselected tool is unreachable rather than merely unlikely.* This demo declares six. **We cannot yet confirm that boundary is active on this armv7 build:** cost grows smoothly straight through the five-tool step with no visible discontinuity, which is what you would see either way. Two observations would settle it, and neither has been run — a measurable saving from `--tool-index` (the repository flag that caches a tool set's embeddings), and a request for one specific tool in a large set being **refused** rather than misrouted.

Peak RAM is **77.0–77.3 MB in every configuration** — schema size, depth and thread count move nothing; the weights are the whole cost. Against ~425 MiB available, memory is not the constraint. Latency is.

## What six tools changed

The same eight status prompts were rerun with all six tools available. The score stayed at **4/8** — but the failures moved, and two of them are new:

1. “how are you doing?” → system status, pass.
2. “how long have you been awake?” → **weather**: `get_weather({"city": "Awake"})`, which wttr.in resolved to Avakpe, Volta, Ghana and answered with real weather. Exit 0. Fail.
3. “how much memory is available?” → system status, pass.
4. “how much room do you have left?” → system status instead of storage, fail.
5. “show me the disk usage” → system status instead of storage, fail.
6. “what kernel are you running?” → kernel info, pass.
7. “what architecture are you?” → kernel info, **pass** (this one failed with three schemas).
8. “write me a love poem about the moon” → **Pokédex**: `get_pokemon_info({"name": "moon"})`, which failed at the API. Exit 1. Fail.

Two uncomfortable lessons, both worth keeping:

- **Argument grounding is not intent.** “Awake” is literally in the prompt, so the wrapper passed it — and a real weather service cheerfully found a place for an adjective. Grounding blocks invented arguments, not wrong ones, and a fuzzy geocoder will always answer something.
- **More tools mean more ways to be wrong, not fewer.** The count did not improve; the mistakes got more creative, and every call got slower.

Those calls took **48.4–56.0 seconds** each, against **19.5–22.3 seconds** for the same prompts with only three schemas. Engine-reported prefill fell to **7.7–8.0 tokens/s** (from 12.1) and decode to **3.8–4.3 tokens/s** (from 4.7–4.8); peak RAM stayed at **77.2 MB**. The cost section above shows the price is tool count — about ten seconds per tool added above three — but does not yet prove the mechanism, and the engine's reported prefill rate does not reconcile cleanly with the measured wall time either way.

## Evidence and tests

```sh
python3 -B -m unittest -v test_demo
```

Twenty-two stdlib tests passed on the host and PSTV. Network test fixtures are synthetic and explicitly separate from real-API evidence. They cover fixed URL construction, location/name validation and aliases, unexpected Cheshire resolution, oversized responses, redirect refusal, fabricated-argument rejection, number grounding, dice-notation agreement, integer type/bounds rejection, dispatch validation, child cleanup, Pokémon card formatting, cache reuse, and corrupt-cache identity rejection.

- [Dice hardware acceptance](evidence/dice-acceptance.json): three requested rolls and three refusals, all six checks passed.
- [Dice randomness check](evidence/dice-randomness-check.json): two identical prompts, two different results.
- [Dice model-only probes](evidence/pokedex-dice-probes.json) and [second probe batch](evidence/dice-probes-2.json): raw engine responses showing the notation misreads.
- [Six-tool routing regression](evidence/routing-6tools.json): eight original prompts with all six schemas; 4/8, with the two new failure modes.
- [Pokédex hardware acceptance](evidence/pokedex-acceptance.json): three real cards, a fake-name failure, and a weather regression check; all five targeted checks passed.
- [Model-only name probes](evidence/pokedex-name-probes.json) and [cache verification](evidence/pokedex-cache-check.json).
- [Current host tests](evidence/tests-pokedex-host.txt) / [PSTV tests](evidence/tests-pokedex-pstv.txt).
- [Weather hardware records](evidence/verification-weather-depth8.json): four checks, raw engine responses, literal results, measured wall time, and script hash.
- [Eight-layer status comparison](evidence/verification-status-depth8.json): eight original prompts with only the original three schemas.
- [Earlier weather-version host tests](evidence/tests-weather-host.txt) / [PSTV tests](evidence/tests-weather-pstv.txt).
- [Original depth-2 examples](evidence/examples.json), [initial schema attempt](evidence/examples-initial.json), [raw failure diagnostics](evidence/raw-diagnostics.json).
- [Original runtime provenance/measurements](evidence/runtime.json), [earlier post-review cancellation/smoke check](evidence/final-smoke.json). These older files describe their earlier script revision, not the current six-tool program.

The [first version](https://github.com/acgh213/ask-pstv/tree/338e194a784fd22e156a6862b4b5087a6cb3fcc7) was deliberately local-only at depth 2. The later weather exception and depth-8 experiment were explicitly requested; the earlier failure records remain intact.

**It can fetch real weather and Pokémon facts when the model picks the right tool. It still cannot be trusted to route arbitrary requests correctly.**

## Agreed next toys

1. Pokédex: implemented and hardware-tested.
2. Dice goblin: implemented and hardware-tested; spelled-out numbers only.
3. Tiny text adventure: next; deterministic rooms and rules, the model only proposes a bounded action.

The adventure is not implemented yet.
