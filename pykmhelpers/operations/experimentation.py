import os
import shutil
import tempfile
import traceback
import time


class Experimentation:
    def __init__(self, name, output_dir, data_dir, callback):
        self._name = name
        self._dir = output_dir
        self._data = data_dir
        self._callback = callback
        os.makedirs(self.work_dir(), exist_ok=True)

    def work_dir(self):
        return os.path.join(self._dir, self._name)

    def run(self, data_id, parameters, copy_data, auto_clean):
        results = {}
        for i in data_id:
            results[i] = {}
            start_time = time.time()
            try:
                d = os.path.join(self.work_dir() if copy_data else self._data, i)

                if copy_data:
                    shutil.copytree(os.path.join(self._data, i), d)

                assert os.path.isdir(d)
                results[i]["result"] = self._callback(i, d, parameters)

                if copy_data and auto_clean:
                    shutil.rmtree(d)
            except Exception as e:
                print(e)
                traceback.print_exc()
                results[i]["error"] = str(e)
            finally:
                end_time = time.time()
                duration = end_time - start_time
                results[i]["start_time"] = start_time
                results[i]["end_time"] = end_time
                results[i]["duration"] = duration
        return results


def main():
    """Test simple use cases of the Experience class."""

    # Create temporary directories for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = os.path.join(tmpdir, "output")
        data_dir = os.path.join(tmpdir, "data")
        os.makedirs(data_dir)

        # Create test data
        test_data_ids = ["sample_1", "sample_2", "sample_3"]
        for data_id in test_data_ids:
            data_path = os.path.join(data_dir, data_id)
            os.makedirs(data_path)
            # Create a test file in each data directory
            with open(os.path.join(data_path, f"{data_id}.txt"), "w") as f:
                f.write(f"Test data for {data_id}\n")

        print("Test data created:")
        for data_id in test_data_ids:
            print(f"  - {data_id}")
        print()

        # Test case 1: Run without copying data
        print("=" * 60)
        print("Test 1: Run without copying data (copy_data=False)")
        print("=" * 60)

        def simple_callback(data_id, path, params):
            print(f"  Processing {data_id} with params {params}")
            if os.path.exists(path):
                with open(os.path.join(path, f"{data_id}.txt"), "r") as f:
                    c = f.read().strip()
                    print(f"    Content: {c}")
                    return c

        exp1 = Experimentation("experiment_1", output_dir, data_dir, simple_callback)
        results1 = exp1.run(
            test_data_ids, {"mode": "test"}, copy_data=False, auto_clean=False
        )
        print("\nResults:")
        for data_id, result_data in results1.items():
            print(f"  {data_id}:")
            print(f"    Duration: {result_data['duration']:.4f}s")
            print(f"    Start: {result_data['start_time']}")
            print(f"    End: {result_data['end_time']}")
            print(f"    Result: {result_data['result']}")
        print()

        # Test case 2: Run with data copying and auto-clean
        print("=" * 60)
        print(
            "Test 2: Run with copying data and auto-clean (copy_data=True, auto_clean=True)"
        )
        print("=" * 60)

        exp2 = Experimentation("experiment_2", output_dir, data_dir, simple_callback)
        exp2.run(
            test_data_ids[:1], {"mode": "copy_test"}, copy_data=True, auto_clean=True
        )

        # Verify work directory still exists but copied data is cleaned
        work_dir = exp2.work_dir()
        print(f"  Work directory exists: {os.path.exists(work_dir)}")
        print(
            f"  Work directory contents: {os.listdir(work_dir) if os.path.exists(work_dir) else 'N/A'}"
        )
        print()

        # Test case 3: Run with data copying but no auto-clean
        print("=" * 60)
        print(
            "Test 3: Run with copying data but no auto-clean (copy_data=True, auto_clean=False)"
        )
        print("=" * 60)

        exp3 = Experimentation("experiment_3", output_dir, data_dir, simple_callback)
        exp3.run(
            test_data_ids[:1],
            {"mode": "copy_no_clean"},
            copy_data=True,
            auto_clean=False,
        )

        # Verify copied data remains
        work_dir = exp3.work_dir()
        print(f"  Work directory exists: {os.path.exists(work_dir)}")
        print(
            f"  Work directory contents: {os.listdir(work_dir) if os.path.exists(work_dir) else 'N/A'}"
        )
        print()

        # Test case 4: Run with custom callback
        print("=" * 60)
        print("Test 4: Run with custom callback (counting files)")
        print("=" * 60)

        file_count = {}

        def counting_callback(data_id, path, params):
            print(f"  Processing {data_id} with params {params}")
            count = len(
                [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
            )
            file_count[data_id] = count
            print(f"  {data_id}: {count} files in directory")
            return count

        exp4 = Experimentation("experiment_4", output_dir, data_dir, counting_callback)
        results4 = exp4.run(
            test_data_ids, {"mode": "counting"}, copy_data=False, auto_clean=False
        )
        print("\nResults:")
        for data_id, result_data in results4.items():
            print(f"  {data_id}:")
            print(f"    Result: {result_data['result']}")
            print(f"    Duration: {result_data['duration']:.4f}s")
        print(f"  Summary: {file_count}")
        print()


if __name__ == "__main__":
    main()
