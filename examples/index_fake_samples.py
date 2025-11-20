from kmhelpers import Main, Toolbox, KmindexWrapper
import os

# Initialize the environment
Main.init(chdir=os.path.dirname(os.path.abspath(__file__)))

sample_dir = "data/fake_samples"
index_id = "data/fake_samples_index"
fof_file = "data/fake_samples.fof"

# Create wrapper
wrapper = KmindexWrapper()

wrapper.fof_manager.create_fof_from_directory(sample_dir, fof_file)

# Build a presence/absence index
index = wrapper.build(
    index_path=index_id, fof_file=fof_file, kmer_size=31, bloom_size=10000000
)

# Query the index
# results_dir = wrapper.query(
#     index="my_index",
#     query_file="query.fasta",
#     output_dir="query_results"
# )

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
