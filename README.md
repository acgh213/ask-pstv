# ask-pstv

A tiny, manual CLI experiment: ask a Linux-running PlayStation TV about itself, using [Cactus Compute Needle 3](https://github.com/cactus-compute/needle) locally.

**Status: partial / failed acceptance.** The wrapper runs on real PSTV hardware, but the unchanged two-layer model chose the expected action for only **4 of 8 canned prompts**, both before and after a small schema cleanup. It incorrectly routes storage questions and an irrelevant poetry request to system status. It is **not** a reliably rejecting natural-language interface. The experiment stopped rather than adding keyword routing, changing depth, or training anything.

## What does work

Actual output from the final hardware check, not an illustrative fixture:

```text
$ ./ask-pstv "how are you doing?"
Needle -> get_system_status({})

PSTV:
  uptime: 5d 18:22:09
  memory available: 433.6 MiB
  load (1/5/15 min): 2.00 / 2.23 / 1.19
```

`"what kernel are you running?"` selected `get_kernel_info({})` and returned Linux `6.12.0-g37b9348710df`, architecture `armv7l`.

One invocation runs one foreground inference child, validates its JSON, reads at most one local status tool, formats the result, and exits. The model never writes the answer prose. Status is sampled **after** the inference process exits: available memory has largely recovered, but load averages still include the inference work.

## Run it on the existing test setup

No packages to install. Python 3 standard library only, on the existing Debian 12 armhf userspace.

Put this directory directly inside the feasibility directory, alongside the existing official runtime/model:

```text
pstv-needle-feasibility-2026-09-19/
├── needle
├── needle3.cact
└── ask-pstv-demo/
    ├── ask-pstv
    └── test_demo.py
```

Then:

```sh
cd /root/pstv-needle-feasibility-2026-09-19/ask-pstv-demo
./ask-pstv "how are you doing?"
./ask-pstv "what kernel are you running?"
./ask-pstv --examples
```

`--examples` only prints the eight prompts; it does not run them. To deploy the repository's code into an existing test directory, copy `ask-pstv` (preserving its executable bit). `test_demo.py` is optional. The one executable script contains the entire demo, schemas included.

Exit codes: `0` = an allowed read-only tool ran (not proof that it was the correct tool); `2` = invalid input or no acceptable single tool decision; `1` = runtime/read failure or timeout; `130` = interrupted.

## Exactly three tools

- `get_system_status({})`: reads `/proc/uptime`, `/proc/meminfo`, `/proc/loadavg`.
- `get_storage_status({})`: reads `statvfs` for `/` and `/mnt/vita-card` when mounted. Reports missing/unmounted card paths explicitly rather than pretending an ordinary directory is a separate filesystem.
- `get_kernel_info({})`: reads `os.uname()` for kernel release, build version, architecture.

No temperature tool: the target exposed no `/sys/class/thermal/thermal_zone*/temp` files during this test. No packages, drivers, or hardware probing were added to obtain one.

## Safety boundary, and what it does not prove

- Tools take **zero arguments**, access fixed local paths, and never execute a shell or use networking.
- A returned name must exactly match the dispatch dictionary. Arguments must be the empty JSON object; extra call fields, unknown names, multiple calls, duplicate JSON keys, malformed/error responses, non-finite/invalid confidence, and suppressed calls fail closed.
- No `eval`, dynamic imports from output, command interpolation, path selection by the model, recursion, retries, or second model call.
- Native executable gets a fixed argv, `--depth 2 --threads 4 --max 128 --fail-input-overflow`. No `--forced`, regex triggers, or keyword-based routing.
- Telemetry is explicitly disabled with `NEEDLE_TELEMETRY=0` and `DO_NOT_TRACK=1`; offline mode is set. No cloud fallback or downloader exists in the wrapper. Its child receives a minimal environment rather than inherited credentials.
- Temporary schema/cache/home files live in a private temporary directory inside the demo directory and are removed on ordinary exit. The existing model/runtime are read, not modified.
- A 180-second inference timeout, disabled core dumps, and a 384 MiB child address-space limit are process-local. Timeout/cancellation kills and reaps the foreground child. SIGKILL or power loss cannot perform Python cleanup and may leave temporary files.
- No daemon, server, socket listener, autostart, Home Assistant, or voice integration. No system configuration changes.

An empty `function_calls` list always means refusal: unused metadata cannot cause dispatch, and is not treated as an independently valid engine attestation. The `PSTV` heading is the demo's label, not a hardware identity check; these functions report the machine on which the script runs. Run it on the console, not on your SSH client.

This is a **dispatch boundary, not an OS sandbox** for the native executable. The prebuilt engine is a trusted dependency; its network activity was not packet-audited. The model can still select the **wrong allowed read-only tool**, including for an irrelevant request. Strict JSON validation does not detect that semantic mistake. Running as root is unnecessary if the user can read the weights and write the demo directory; do not elevate merely to run this script.

## Eight canned prompts: final real-hardware results

1. `how are you doing?` → system status, **pass**.
2. `how long have you been awake?` → system status, **pass**.
3. `how much memory is available?` → system status, **pass**.
4. `how much room do you have left?` → system status instead of storage, **fail**.
5. `show me the disk usage` → system status instead of storage, **fail**.
6. `what kernel are you running?` → kernel info, **pass**.
7. `what architecture are you?` → system status instead of kernel info, **fail**.
8. `write me a love poem about the moon` → system status instead of rejection, **fail**.

Final observed CLI duration was **21.055–23.703 seconds including SSH overhead**. These are not model-load times. All eight processes exited 0, which is exactly why exit status alone was not an acceptance test.

The diagnostic poetry response gave the wrong call confidence **1.0** and this reasoning:

> 'write me a love poem about the moon' -> get_system_status to see what's available.

The wrapper does not implement the implied follow-up step. It reads the selected status once and exits. A confidence-only threshold cannot distinguish this wrong answer from the tested right ones.

## Evidence and tests

- [`evidence/examples.json`](evidence/examples.json): final eight prompts, expected decisions, literal CLI output, exit codes, timings, pass flags.
- [`evidence/examples-initial.json`](evidence/examples-initial.json): initial longer descriptions/system instructions, also 4/8. The final pass shortened descriptions and omitted system instructions per [the official schema guide](https://cactuscompute.com/blog/designing-tools-for-needle).
- [`evidence/raw-diagnostics.json`](evidence/raw-diagnostics.json): two additional raw model responses explaining the storage/poetry failures. These diagnostic calls did **not** execute status tools.
- [`evidence/runtime.json`](evidence/runtime.json): artifact identity and measurements from the preceding model feasibility test.
- [`evidence/final-smoke.json`](evidence/final-smoke.json): after the review fixes, a real kernel query, the still-misrouted poetry query, a direct read-only storage check (not model-routed), and successful SIGTERM cancellation with no runtime process or temporary directory left over.
- `test_demo.py`: nine stdlib safety tests, including explicitly synthetic malformed-response fixtures and process-cleanup mocks. These are separate from hardware evidence. Review found an oversized-confidence integer could overflow a float conversion; validation now rejects it using a bounded numeric comparison. The child gets its own process group, which is killed on exit/timeout/cancellation before the direct child is reaped.

```sh
python3 -B -m unittest -v test_demo
```

The earlier feasibility run achieved **4.8 decode tokens/s**, **12.9–13.8 prefill tokens/s**, and **77.2–77.3 MiB peak process RSS**, with simple weather/timer schemas. Those numbers are not measurements of every wrapper invocation. Final diagnostic calls reported **4.7–4.8 decode tokens/s**, **12.1–12.5 prefill tokens/s**, and **77.2 MiB peak RAM**. The runtime file is 986,100 bytes and weights are 35,335,380 bytes; `--depth 2` changes execution depth, not the size of the full weight archive.

## Where it stops

No retraining, export, compilation, different model, changed depth, packages, or system changes. No hidden keyword fallback. Improving routing would be a separate decision, not something silently added to make the screenshots look better.

**The PSTV can run Needle. This particular zero-argument, two-layer demo does not yet pass its natural-language routing test.**
