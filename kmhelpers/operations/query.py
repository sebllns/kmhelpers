class KmindexQueryResult:
    def __init__(self, result: dict) -> None:
        self._result = result

    @property
    def result(self):
        return self._result
    
    def get_index_result(self, index_id) -> dict :
        return self.result.get(index_id, dict)

class KmindexQuery:
    def __init__(self, path: str = "", sequence: str = "") -> None:
        assert path or sequence, "Either path or sequence string must be provided"
        if sequence:
            if path:
                pass
        pass

    def run_query(self, registry_path : str, index_ids: list[str] = []):
        pass