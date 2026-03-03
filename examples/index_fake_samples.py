from pykmhelpers import Main, Toolbox, KmindexWrapper
import os
import tempfile
import shutil

temp_dir = tempfile.mkdtemp(
    prefix="index_fake_samples_",
    dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
)

# Initialize the environment
Main.init(chdir=temp_dir)

sample_dir = "../fake_samples"
registry = "fake_index"
fof_file = "fake_samples.fof"
query_file = "../q_sample_001.fasta"

# Create wrapper
wrapper = KmindexWrapper()

wrapper.fof_manager.create_fof_from_directory(sample_dir, fof_file, recursive=True)

# Build a presence/absence index
index = wrapper.build(
    output_registry_path=registry,
    input_fof_file=fof_file,
    kmer_size=31,
    bloom_size=10000000,
)

# Query the index
results_dir = wrapper.query(input_registry=registry, query_file=query_file, output_dir="q1")

# Or use the index object directly
# results_dir = wrapper.query(
#     index=index,
#     query_file="query.fasta",
#     output_dir="query_results2"
# )

# Access index properties
print(f"K-mer size: {index.kmer_size}")
print(f"Number of samples: {index.nb_samples}")
print(f"Sample names: {index.samples}")

# if os.path.exists(temp_dir):
#     shutil.rmtree(temp_dir)
