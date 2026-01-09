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
