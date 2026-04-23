import os
from typing import IO


class Cache:
    def __init__(self, path: str):
        os.makedirs(path, exist_ok=True)
        self._path = path
        self._handles: dict[str, IO[str]] = {}

    def _table_path(self, table: str) -> str:
        return os.path.join(self._path, table)

    def _get_handle(self, table: str) -> IO[str]:
        """Return a cached open append handle for table, opening it if needed."""
        if table not in self._handles:
            self._handles[table] = open(self._table_path(table), "a")
        return self._handles[table]

    def write(self, table: str, key: str, value: str) -> None:
        """Append key-value pair to table and flush to disk immediately."""
        fh = self._get_handle(table)
        fh.write(f"{key}\t{value}\n")
        fh.flush()
        os.fsync(fh.fileno())

    def read(self, table: str) -> dict[str, str]:
        """Read table and return a dict of key -> value.

        Later entries override earlier ones (last-write-wins).
        Returns an empty dict if the table file does not exist.
        """
        table_file = self._table_path(table)
        if not os.path.exists(table_file):
            return {}
        result: dict[str, str] = {}
        with open(table_file, "r") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if "\t" not in line:
                    continue
                key, _, value = line.partition("\t")
                result[key] = value
        return result

    def close(self) -> None:
        """Flush and close all open table handles."""
        for fh in self._handles.values():
            try:
                fh.flush()
                fh.close()
            except OSError:
                pass
        self._handles.clear()

    def clear(self, table: str) -> None:
        """Close and delete a table file if it exists."""
        if table in self._handles:
            try:
                self._handles.pop(table).close()
            except OSError:
                pass
        table_file = self._table_path(table)
        if os.path.exists(table_file):
            os.remove(table_file)

    def exists(self, table: str) -> bool:
        return os.path.exists(self._table_path(table))

    def delete(self) -> None:
        """Close all handles and delete the entire cache directory."""
        import shutil

        self.close()
        if os.path.exists(self._path):
            shutil.rmtree(self._path)

    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @staticmethod
    def get_cache_dir(workdir, id) -> str:
        return os.path.join(workdir, ".kmhelpers_cache", id)
