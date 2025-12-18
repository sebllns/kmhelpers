class Sequence:
    def __init__(self, content: str = "", header: str = "") -> None:
        self._content = content
        self._header = header

    @property
    def length(self) -> int:
        return len(self._content)

    @property
    def content(self) -> str:
        return self._content

    @property
    def header(self) -> str:
        return self._header

    def __str__(self) -> str:
        return self.content

    def __repr__(self) -> str:
        return f"Sequence(len='{self.length}')"

    def to_fasta(self) -> str:
        """Return FASTA formatted string with header and sequence."""
        lines = []
        if self._header:
            lines.append(f">{self._header}")
        lines.append(self._content)
        return "\n".join(lines)

