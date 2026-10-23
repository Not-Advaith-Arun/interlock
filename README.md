# Interlock

**Find the event sequence where two individually safe changes fail together.**

A bounded behavioral merge checker for explicit asynchronous models. Interlock explores a base, two branches, and their proposed merge under the same schedule, then emits a reproducible interaction witness.

## Try the interactive showcase

Python 3.10+; standard library only.

```sh
git clone https://github.com/Not-Advaith-Arun/interlock.git
cd interlock
python3 -m interlock showcase -o /tmp/interlock-showcase.html
```

Open `/tmp/interlock-showcase.html` for a four-version comparison and interactive witness stepper, built from computed fictional examples.

## Reproduce a conflict

```sh
python3 -m interlock check examples/retry_conflict.json \
  --fixture retry-conflict --witness /tmp/retry.witness.json
python3 -m interlock replay /tmp/retry.witness.json --fixture retry-conflict
```

Both commands intentionally exit **1** when they find/reproduce the failure:

```text
base PASS · left PASS · right PASS · merged FAIL
submit → deliver → timeout → deliver
```

One change adds retries; another removes worker deduplication. Either change passes individually. Together they allow one logical job to produce two effects. Bundled handlers independently check the model, and source-pinned witnesses refuse changed fixture identities.

## Scope

A working research prototype. It requires caller-supplied model configurations and supports declared bundled source fixtures. It does **not** inspect arbitrary Git branches, infer application models, or prove unbounded safety. Depth/state limits and incomplete exploration are explicit. Historical CPython calibration is a separate Linux/bubblewrap workflow, not a general merge-analysis claim.

## Validation

```sh
python3 -m interlock suite
python3 -m unittest discover -s tests -v
```

The suite covers bundled conflict/control cases against real handlers. `python3 -m interlock --help` lists commands and exit codes.
