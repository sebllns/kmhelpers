# pipeline

Run a sequence of commands defined in a YAML pipeline file.

## Usage

```
kmhelpers pipeline [OPTIONS] PIPELINE_FILE
```

## Description

`pipeline` executes a series of `kmhelpers` commands in order, as defined in a YAML file. Steps run sequentially. Use `-x` to override parameters for all steps at runtime.

## Pipeline File Formats

### Dict format (simple, no repeated commands)

```yaml
compose:
  workdir: /path/to/workdir
  input_files: [samples.yaml]
apply:
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

## Examples

```bash
# Run a pipeline
kmhelpers pipeline my_pipeline.yaml

# Override workdir and threads for all steps
kmhelpers pipeline my_pipeline.yaml -x workdir /tmp -x threads 16
```

## Options

| Option | Description |
|--------|-------------|
| `PIPELINE_FILE` | YAML pipeline definition file |
| `-x KEY VALUE` | Override a parameter for all steps (repeatable) |