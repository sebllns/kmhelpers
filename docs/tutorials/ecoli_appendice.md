
## Going Further

### Build an index with [`apply`](../commands/apply.md)

```bash
kmhelpers apply coli3682_db/index.yaml -w coli3682_db/ -t 8
```

`apply` runs the build. The `-t 8` flag sets the number of threads; adjust it
to match your machine.

Useful options for long runs:

```bash
# Show a progress bar
kmhelpers apply coli3682_db/index.yaml -w coli3682_db/ -t 8 --show-progress

# Abort immediately on any error
kmhelpers apply coli3682_db/index.yaml -w coli3682_db/ -t 8 --fail-on-error

# Get an email when the build finishes
kmhelpers apply coli3682_db/index.yaml -w coli3682_db/ -t 8 \
    --notify you@example.com
```

Once complete, the index is registered in `coli3682_db/` and ready to query.

### Query the index with advanced options ([`query`](../commands/query.md))

Results are written in JSON by default. Use `-f` to change the format:

```bash
# CSV output
kmhelpers query -r coli3682_build/ -o results/ -f csv query.fa

# Print results to the console as well
kmhelpers query -r coli3682_build/ -n index -o results/ -p query.fa
```

To query all sequences together as a single batch (one result row instead of
one per sequence):

```bash
kmhelpers query -r coli3682_db/ -n index -o results/ \
    --single-query my_batch query.fa
```

Use `-R` to filter out low-confidence hits (fraction of shared k-mers below
the threshold):

```bash
kmhelpers query -r coli3682_db/ -n index -o results/ -R 0.5 query.fa
```

### Next steps

- **Compress** the index to save disk space:
  ```bash
  kmhelpers compress -r coli3682_db/ -n index --reorder
  ```
- See the [Command Reference](../commands/index.md) for the full option list of
  every command used here.


# 3682

This tutorial walks through the full kmhelpers workflow on a real public dataset:
3 682 *E. coli* assemblies downloaded from NCBI and archived on Zenodo.

> Jarno N. Alanko. (2022). * E. coli assemblies from NCBI* [Data set].
> Zenodo. <https://doi.org/10.5281/zenodo.6577997>