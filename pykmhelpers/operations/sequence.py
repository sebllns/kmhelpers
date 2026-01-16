class Sequence:
    def __init__(self, content: str = "", header: str = "") -> None:
        self._content = content
        self._header = header

    @property
    def length(self) -> int:
        """Get number of nucleotides."""
        return len(self._content)

    @property
    def content(self) -> str:
        return self._content

    @property
    def header(self) -> str:
        return self._header

    def __repr__(self) -> str:
        return f"Sequence(len='{self.length}')"

    def __str__(self) -> str:
        return self.to_fasta()
    
    def __len__(self) -> int:
        return self.length

    def to_fasta(self) -> str:
        """Return FASTA formatted string with header and sequence."""
        lines = []
        if self._header:
            lines.append(f">{self._header}")
        lines.append(self._content)
        return "\n".join(lines)

    def fill_random(self, length):
        import random
        self._content = ''.join(random.choice('ACGT') for _ in range(length))

    def fill_random_kmers(self, n: int, k: int) -> None:
        """Generate a sequence containing n random unique consecutive k-mers of size k.

        Uses a sliding window approach where each k-mer overlaps the previous by k-1 bases.
        This ensures all n k-mers appear consecutively in the resulting sequence.

        Args:
            n: Number of unique k-mers to generate
            k: Size of each k-mer

        Raises:
            ValueError: If k or n are not positive, or if unable to generate n unique k-mers
        """
        import random

        if k <= 0:
            raise ValueError(f"k-mer size must be positive, got {k}")
        if n <= 0:
            raise ValueError(f"Number of k-mers must be positive, got {n}")

        # Generate first k-mer randomly
        sequence = ''.join(random.choice('ACGT') for _ in range(k))
        kmers_seen = {sequence}

        # Generate remaining n-1 k-mers using sliding window
        for _ in range(n - 1):
            found = False
            nucleotides = ['A', 'C', 'G', 'T']
            random.shuffle(nucleotides)

            for nuc in nucleotides:
                # Append nucleotide and extract last k bases as new k-mer
                new_sequence = sequence + nuc
                new_kmer = new_sequence[-k:]

                if new_kmer not in kmers_seen:
                    sequence = new_sequence
                    kmers_seen.add(new_kmer)
                    found = True
                    break

            if not found:
                raise ValueError(
                    f"Could not generate {n} unique k-mers of size {k}. "
                    f"Generated {len(kmers_seen)} unique k-mers before getting stuck."
                )

        self._content = sequence

    def fill_random_and_count_kmers(self, L: int, k: int) -> int:
        """Fill sequence with random nucleotides and count distinct k-mers.

        Args:
            L: Length of the random sequence to generate
            k: Size of each k-mer

        Returns:
            Count of distinct k-mers in the generated sequence

        Raises:
            ValueError: If L or k are not positive, or if k > L
        """
        import random

        if L <= 0:
            raise ValueError(f"Sequence length must be positive, got {L}")
        if k <= 0:
            raise ValueError(f"k-mer size must be positive, got {k}")
        if k > L:
            raise ValueError(f"k-mer size ({k}) cannot exceed sequence length ({L})")

        # Generate random sequence of length L
        self._content = ''.join(random.choice('ACGT') for _ in range(L))

        # Extract all k-mers and count distinct ones
        kmers = set()
        for i in range(L - k + 1):
            kmer = self._content[i:i + k]
            kmers.add(kmer)

        return len(kmers)
