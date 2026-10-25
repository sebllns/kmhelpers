# pipeline

## Synopsis

Run a sequence of commands defined in a YAML pipeline file.

!!! abstract "USAGE"
    ```
    kmhelpers pipeline [OPTIONS] PIPELINE_FILE
    ```

    | Argument | Description |
    |----------|-------------|
    | `PIPELINE_FILE` | YAML pipeline definition file (required) |

!!! abstract "I/O"
    **Input:** YAML pipeline definition file  
    **Output:** depends on pipeline steps

## Advanced Options
| Option | Description |
|--------|-------------|
| `-x KEY VALUE` | Override a parameter for all steps (repeatable) |

## Description

`pipeline` executes a series of `kmhelpers` commands in order, as defined in a YAML file. Steps run sequentially. Use `-x` to override parameters for all steps at runtime.

**Priority** - global config (`-C`) < pipeline YAML < `-x` overrides.

## Pipeline File Formats

### Dict format (simple, no repeated commands)

```yaml
compose:
  workdir: /path/to/workdir
  input_files: [samples.yaml]
build:
  workdir: /path/to/workdir
  threads: 8
```

### List format (allows repeating the same command)

```yaml
- apply:
    workdir: /path/a
    input_files: [a.yaml]
- apply:
    workdir: /path/b
    input_files: [b.yaml]
```

## Running a command again

The reports of `design` (`DESIGN_DIR/logs/`), `plan`, `apply` and `build` (`BUILD_DIR/logs/`) start with a `run` block:

```yaml
run:
  command: kmhelpers design samples.jsonl -o db -n metav -s initial --sb '2**34'
  cwd: /home/me/shared              # the folder it was run from: relative paths are from there
  step:                             # the command as a pipeline step: the options given
  - design:
      input: samples.jsonl
      output_dir: db
      name: metav
      session_id: initial
      shard_budget: 2**34
  defaults:                         # the other options, at their default then
    base: 1.1
    ...
  globals:                          # kmhelpers options given before the command (-Y, -V, -C FILE...)
    verbose: 1
```

A report is a pipeline file: `kmhelpers pipeline REPORT` runs its `step` again, from the current folder (`cd` to its `cwd` first). `-x` changes an option, e.g. `-x output_dir db2` to design into another folder.

- Only the options given are in `step`: an option left out takes its current default, which `defaults` shows as it was then. The values a `-C` file gave count as given.
- Options that only act on that run are left out: `--redesign`, `--replan`, `--status`, `--pending`, `--sp`, `--interval`. They are still in `command`.
- `globals` are not applied: pass them to `kmhelpers` again (e.g. `kmhelpers -Y pipeline REPORT`).
- A command run by `kmhelpers pipeline` records no `step`: the pipeline file is its record. Its `run` gives that file (`pipeline`) and the pipeline command line (`command`); run that pipeline to run it again. `kmhelpers pipeline` refuses its report.
- `history.tsv` lists every run of a folder, one line each: `time`, `report` (`design`, `plan`, `apply`; a `build` writes a `plan` and an `apply` line), `status`, `duration_s`, `command`.

## Examples

```bash
# Run a pipeline
kmhelpers pipeline my_pipeline.yaml

# Override workdir and threads for all steps
kmhelpers pipeline my_pipeline.yaml -x workdir /tmp -x threads 16

# Run a design again, into another folder
kmhelpers pipeline db/logs/kmhelpers_design_20261025_024824.yaml -x output_dir db2
```