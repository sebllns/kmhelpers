from ..core import KmindexWrapper, KmtricksIndex, KmindexRegistry, Toolbox
from ..operations import FofManager
import os


class IndexBuilder:
    def __init__(self, output_index_path):
        """Initialize the IndexBuilder."""
        self._path = Toolbox.get_canonical_path(output_index_path)
        os.makedirs(self.path, exist_ok=True)
        self._registry = KmindexRegistry(os.path.join(self.path, "registry"))

    @property
    def index(self):
        return self._registry

    @property
    def path(self):
        return self._path

    def create_subindex(self, name, samples):
        wrapper = KmindexWrapper()
        fof = FofManager(samples=samples)
        fof_path = os.path.join(self.path, f"{name}.fof")
        fof.save(fof_path=fof_path)
        wrapper.build(fof_path, self.index.root_path, )

