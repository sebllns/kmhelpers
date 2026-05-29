import kmparams

p = kmparams.kmtricks_params(
    kmers=137_438_953_471,
    memory=33_050_427_392,
    files=1_073_741_816,
    partitions=256,
    samples=7397,
)
print("PROCESS...")

# p.nb_threads_partitions()
# p.nb_partitions()
# p.nb_open_files()

p.auto()

print("RESULT")
print(p)
