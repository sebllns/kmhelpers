# Getting Started

This guide walks through a typical workflow: discovering samples, profiling them, composing index definitions, building indices, and querying them.

## Typical Workflow

```
list → profile → compose → plan → apply → query
```

## Step 1 — Discover samples

Scan a directory of sequence files and produce a YAML sample manifest with k-mer counts:

```bash
kmhelpers list samples.yaml -i /path/to/sequences -k 31 --count
```

This generates `samples.yaml` with one entry per sample (grouped by leaf folder by default).

## Step 2 — Profile the samples

Analyse k-mer counts to determine the optimal Bloom-filter span configuration:

```bash
kmhelpers profile -i samples.yaml -o ./profile_output -p 0.05
```

Outputs `span_distribution.csv` and a plot showing span assignments.

## Step 3 — Compose index definitions

Generate index definition files from the sample manifest:

```bash
kmhelpers compose samples.yaml -o ./db -k 31
```

Use `--split` to partition across multiple sub-indices:

```bash
kmhelpers compose samples.yaml -o ./db --split
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

## Automating with a Pipeline

Combine multiple steps into a single YAML pipeline file:

```yaml
compose:
  workdir: /path/to/db
  input_files: [samples.yaml]
apply:
  workdir: /path/to/db
  threads: 8
```

Run it:

```bash
kmhelpers pipeline my_pipeline.yaml
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