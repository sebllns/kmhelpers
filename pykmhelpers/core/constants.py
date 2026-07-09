from pykmhelpers import __version__
from pykmhelpers._commit import GIT_COMMIT

KMHELPERS_VERSION = __version__
KMHELPERS_COMMIT = GIT_COMMIT

DATA_EXT = (
    ".fasta.gz",
    ".fastq.gz",
    ".fa.gz",
    ".fq.gz",
    ".fna.gz",
    ".fasta",
    ".fastq",
    ".fa",
    ".fq",
    ".fna",
)

COMPRESS_EXT = (".gz", ".bz2", ".zip", ".xz")
