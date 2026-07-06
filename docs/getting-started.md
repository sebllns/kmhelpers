# Getting Started

This guide walks through a typical workflow: discovering samples, profiling them, composing index definitions, building indices, and querying them.

> **Tip:** `kh` is available as a short alias for `kmhelpers` — both commands are identical.

## Typical Workflow

![Pipeline diagram](diagrams/fig_pipeline_mini_animation.svg)


```
list → profile → compose → plan → apply → query
```

![Pipeline diagram](diagrams/fig_pipeline.svg)


## Step 1 — Discover samples

Scan a directory of sequence files and produce a YAML sample manifest with k-mer counts:

```bash
kmhelpers list samples.jsonl -i /path/to/sequences -k 25
```

This generates `samples.jsonl` with one entry per sample.

## Step 2 — Profile the samples

Analyse k-mer counts to determine the optimal Bloom-filter span configuration:

```bash
kmhelpers profile -i samples.jsonl -o ./profile_output -p 0.25
```

Outputs `./profile_output/profile.yaml` and a plot showing span groups.

## Step 3 — Compose index definitions

Generate index definition files from the sample manifest:

```bash
kmhelpers compose samples.jsonl -o ./db
```

## Step 4 — Preview the build plan

Dry-run to validate paths and see what will be built:

```bash
kmhelpers plan index.yaml -w /output
```

## Step 5 — Build indices

```bash
kmhelpers apply index.yaml -w /output
```

Build only specific spans or index names:

```bash
kmhelpers apply index.yaml -w /output --span 28,31 --name my_index
```

## Step 6 — Query

```bash
kmhelpers query -r ./registry -n my_index -o results query.fa
```

Pipe from stdin:

```bash
cat query.fa | kmhelpers query -r ./registry -n my_index -o results -
```

## Global Options

These options apply to every command:

| Option | Description |
|--------|-------------|
| `-v` / `-vv` | Increase verbosity (INFO / DEBUG) |
| `-q` / `-qq` | Decrease verbosity (ERROR / CRITICAL) |
| `-C FILE` | Load default values from a YAML config file |
| `-L FILE` | Write logs to a file |
| `-y` | Skip all confirmation prompts |
| `--chdir DIR` | Change working directory before running |


## Automating with a Pipeline (advanced)

Combine multiple steps into a single YAML pipeline file:

```yaml
compose:
  workdir: /path/to/db
  input_files: [samples.jsonl]
apply:
  workdir: /path/to/db
  threads: 8
```

Run it:

```bash
kmhelpers pipeline my_pipeline.yaml
```
