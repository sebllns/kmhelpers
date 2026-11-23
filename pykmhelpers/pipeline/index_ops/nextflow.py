"""The ``main.nf`` written by ``plan --cluster`` with ``type: nextflow``.

The workflow is the same for every plan: it reads the jobs of the plan
(``jobs.tsv``: shard, job, kind) and those not done yet (``pending.txt``,
from ``apply --pending``), and runs each with ``kmhelpers apply --task``. The
per-plan values (commands, paths, resources) are in ``nextflow.config``.
"""

MAIN_NF = r"""// Written by kmhelpers plan: runs the jobs of the plan with Nextflow.
// Each job runs `kmhelpers apply --task`, which skips what is already done,
// so Nextflow caches nothing (cache = false in nextflow.config).
nextflow.enable.dsl = 2

process BUILD {
    label 'build'
    tag "${job}"
    errorStrategy 'ignore'

    input:
    tuple val(shard), val(job)

    output:
    tuple val(shard), val(job)

    script:
    "${params.apply} --task '${job}'${params.shard_mail}"
}

process PUBLISH {
    label 'publish'
    tag "${shard}"
    errorStrategy 'ignore'

    input:
    val shard

    output:
    val shard

    script:
    "${params.apply} --task '${shard}_publish'${params.shard_mail}"
}

process FINISH {
    label 'check'
    tag 'finish'

    input:
    val ended

    script:
    "bash '${params.finish}'"
}

workflow {
    def pending = file(params.pending).readLines().findAll { it } as Set
    def rows = file(params.jobs).readLines().findAll { it }
        .collect { it.split('\t') as List }
        .findAll { it[1] in pending }
    def builds = rows.findAll { it[2] == 'build' }
    def publishes = rows.findAll { it[2] == 'publish' }.collect { it[0] } as Set
    def count = builds.countBy { it[0] }

    built = BUILD(Channel.fromList(builds.collect { [it[0], it[1]] }))
    // a shard publishes once all its pending build jobs succeeded: a failed
    // job emits nothing, so the group of its shard is never complete
    ready = built
        .filter { shard, job -> shard in publishes }
        .map { shard, job -> [groupKey(shard, count[shard]), job] }
        .groupTuple()
        .map { key, jobs -> key.toString() }
    direct = Channel.fromList((publishes - count.keySet()) as List)
    published = PUBLISH(ready.mix(direct))
    // after every job, successful or not
    FINISH(built.map { it[1] }.mix(published).collect().ifEmpty([]))
}
"""


def groovy(value) -> str:
    """``value`` as a single-quoted Groovy string."""
    text = str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"'{text}'"
