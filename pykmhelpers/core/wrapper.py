import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, List, Optional

import psutil

from pykmhelpers.core.utils import Toolbox

logger = logging.getLogger(__name__)

SAMPLE_EVERY = 1.0  # seconds between two calls of the on_sample of _monitor_cmd


# class BinNotFoundError(FileNotFoundError):
#     pass


class Wrapper:
    def __init__(
        self,
        main_cmd: str,
        dry_run: bool = False,
    ) -> None:
        self.dry_run = dry_run
        self._main_cmd = main_cmd

        if self.env_var in os.environ:
            logger.debug(f"Add {self.env_path} to PATH (from {self.env_var})")
            os.environ["PATH"] = (
                f"{self.env_path}{os.pathsep}{os.environ.get('PATH', '')}"
            )

        which = shutil.which(self.main_cmd)
        if not which:
            raise FileNotFoundError(
                f"{self.main_cmd} not found. Either add its installation directory to PATH, or set the {self.env_var} environment variable to that directory."
            )
        self._which: str = which
        logger.debug(f"Found {self._which}")

    @property
    def main_cmd(self) -> str:
        return self._main_cmd

    @property
    def env_var(self) -> str:
        return f"{os.path.basename(self.main_cmd).upper()}_BIN_PATH"

    @property
    def env_path(self) -> Optional[str]:
        path = os.environ.get(self.env_var)
        if path:
            return Toolbox.get_canonical_path(path)
        return None

    @property
    def which(self) -> str:
        return self._which

    def _run_byte_cmd(
        self,
        cmd: List[Any],
        input: bytes,
    ) -> subprocess.CompletedProcess:
        if self.dry_run:
            result = subprocess.CompletedProcess[str]([str(arg) for arg in cmd], 0)
        else:
            # Run command
            result = subprocess.run(
                [str(arg) for arg in cmd], capture_output=True, input=input, text=False
            )

        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"Command {cmd[0]} returned code {result.returncode}\nLog: {result.stderr.decode(errors='replace').strip()}"  # type: ignore
            )
        return result

    def _run_cmd(
        self,
        cmd: List[Any],
        print_trace: Optional[bool] = None,
        log_file: Optional[str] = None,
        log_errors_only: Optional[bool] = None,
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a command using subprocess and capture its output.

        Args:
            cmd: Command and arguments as a list (converted to List[str])
            print_trace: Whether to print command output (default: computed from logger level)
            log_file: Optional path to write stdout/stderr to
            log_errors_only: Whether to log only errors (default: computed from logger level)

        Returns:
            CompletedProcess with stdout and stderr

        Raises:
            subprocess.SubprocessError: If command returns non-zero exit code
        """
        # Compute print_trace from logger level if not explicitly provided
        if print_trace is None:
            print_trace = logger.isEnabledFor(logging.DEBUG)

        if log_errors_only is None:
            log_errors_only = logger.getEffectiveLevel() >= logging.WARNING

        if self.dry_run:
            result = subprocess.CompletedProcess[str]([str(arg) for arg in cmd], 0)
        else:
            # Run command
            result = subprocess.run(
                [str(arg) for arg in cmd], capture_output=True, text=True
            )

        # Build output content
        output_lines = [
            f"Command: {' '.join(str(arg) for arg in cmd)}",
        ]

        if not log_errors_only and result.stdout.strip():
            output_lines.extend(["\n--- STDOUT ---", result.stdout])

        if result.stderr.strip():
            output_lines.extend(["\n--- STDERR ---", result.stderr])

        output_content = "\n".join(output_lines) if log_file or print_trace else ""

        # Print to console if print_trace is enabled
        if print_trace:
            logger.debug(output_content)

        # Write to log file if specified
        if log_file:
            logger.debug(f"Logging output to: {log_file}")
            with open(log_file, "w") as f:
                f.write(output_content)

        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"Command {cmd[0]} returned code {result.returncode}\nLog: {result.stderr}"
            )
        return result

    def _monitor_cmd(
        self,
        cmd: List[Any],
        print_trace: Optional[bool] = None,
        log_file: Optional[str] = None,
        log_errors_only: Optional[bool] = None,
        on_sample: Optional[Callable[[int], None]] = None,
    ) -> Optional[dict]:
        """
        Run a command and monitor its resource usage.
        Args:
            cmd: Command and arguments as a list
            print_trace: Whether to print trace output. If None, computed from logger level (True if DEBUG).
            log_file: Optional path to write stdout/stderr to. With stdout logged
                (not ``log_errors_only``), stdout is written as it comes, so the
                log can be read while the command runs; stderr and the resource
                usage are appended at the end.
            on_sample: Called with the RSS (bytes) of the process tree, every
                ``SAMPLE_EVERY`` seconds while it runs
        Returns:
            Tuple of (stdout, resource_stats) where resource_stats contains:
                - start_time: Command start timestamp
                - execution_time_s: Execution time in seconds
                - max_cpu_percent: Maximum CPU usage percentage
                - max_memory_mb: Maximum memory usage in MB
                - return_code: Command exit code
                - error: Error message if command failed
            Returns None if process cannot be started
        """
        _cmd = [str(arg) for arg in cmd]

        if self.dry_run:
            return {"command": " ".join(_cmd)}

        # Compute print_trace from logger level if not explicitly provided
        if print_trace is None:
            print_trace = logger.isEnabledFor(logging.DEBUG)

        if log_errors_only is None:
            log_errors_only = logger.getEffectiveLevel() >= logging.WARNING

        # the log stdout is written to as it comes, if any
        stream = log_file if log_file and not log_errors_only else None
        max_cpu = 0.0
        max_memory = 0.0
        monitoring = True
        monitor_lock = threading.Lock()

        def monitor_resources(process):
            nonlocal max_cpu, max_memory
            last_sample = 0.0
            try:
                psutil_process = psutil.Process(process.pid)
                psutil_process.cpu_percent(interval=0.1)

                while monitoring and process.poll() is None:
                    try:
                        processes = [psutil_process] + psutil_process.children(
                            recursive=True
                        )

                        cpu_percent = sum(p.cpu_percent() for p in processes)
                        memory_bytes = sum(p.memory_info().rss for p in processes)
                        memory_mb = memory_bytes / 1024 / 1024

                        with monitor_lock:
                            max_cpu = max(max_cpu, cpu_percent)
                            max_memory = max(max_memory, memory_mb)

                        if on_sample and time.monotonic() - last_sample >= SAMPLE_EVERY:
                            last_sample = time.monotonic()
                            try:
                                on_sample(memory_bytes)
                            except Exception as e:
                                logger.debug(f"Monitoring callback: {e}")

                        time.sleep(0.1)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break
            except Exception as e:
                logger.debug(f"Monitoring: {e}")

        try:
            start_time = time.time()
            result = subprocess.Popen(
                _cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            monitor_thread = threading.Thread(target=monitor_resources, args=(result,))
            monitor_thread.daemon = True
            monitor_thread.start()
            time.sleep(0.01)

            if stream:
                stdout, stderr = self._stream_to_log(result, stream, _cmd)
            else:
                stdout, stderr = result.communicate()
            end_time = time.time()
            monitoring = False
            monitor_thread.join(timeout=1)

            execution_time = end_time - start_time

            with monitor_lock:
                output = {
                    "command": " ".join(_cmd),
                    "start_time": start_time,
                    "execution_time_s": round(execution_time, 4),
                    "max_cpu_percent": round(max_cpu, 4),
                    "max_memory_mb": round(max_memory, 4),
                    "return_code": result.returncode,
                }
                if not log_errors_only:
                    output["stdout"] = stdout
                output["stderr"] = stderr

            usage = [
                f"Execution time: {output['execution_time_s']:.2f}s",
                f"Max CPU: {output['max_cpu_percent']}%",
                f"Max Memory: {output['max_memory_mb']} MB",
                f"Return code: {output['return_code']}",
            ]

            if stream:
                # stdout is in the log already: stderr, then the usage
                tail = ["\n--- STDERR ---", stderr] if stderr.strip() else []
                tail += ["\n--- RESOURCES ---", *usage]
                with open(stream, "a") as f:
                    f.write("\n".join(tail) + "\n")
                if print_trace:
                    logger.debug("\n".join(usage))
                return output

            # Build output content
            output_lines = [f"Command: {output['command']}", *usage]

            if not log_errors_only:
                output_lines.extend(["\n--- STDOUT ---", stdout])

            if stderr.strip():
                output_lines.extend(["\n--- STDERR ---", stderr])

            output_content = "\n".join(output_lines) if log_file or print_trace else ""

            # Print to console if print_trace is enabled
            if print_trace:
                logger.debug(output_content)

            # Write to log file if specified
            if log_file:
                logger.debug(f"Logging output to: {log_file}")
                with open(log_file, "w") as f:
                    f.write(output_content)

            return output

        except Exception as e:
            logger.error(f"Failed to start process: {e}")
            return None

    @staticmethod
    def _stream_to_log(process, log_file: str, cmd: List[str]) -> tuple[str, str]:
        """Write the stdout of ``process`` to ``log_file`` as it comes (``apply
        --status --task`` reads its tail), keep its stderr; both, once it ends."""
        err: list[str] = []
        # read apart: a full stderr pipe would block the process
        reader = threading.Thread(target=lambda: err.append(process.stderr.read()), daemon=True)
        reader.start()
        out: list[str] = []
        with open(log_file, "w") as f:
            f.write(f"Command: {' '.join(cmd)}\n\n--- STDOUT ---\n")
            f.flush()
            for line in process.stdout:
                out.append(line)
                f.write(line)
                f.flush()
        process.wait()
        reader.join()
        return "".join(out), "".join(err)
