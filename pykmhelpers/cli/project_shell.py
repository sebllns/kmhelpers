"""
Interactive shell for kmhelpers projects.
Provides a REPL interface for project-scoped commands using Click for command definition.
"""

import os
import shlex
import click
from pathlib import Path
from click.testing import CliRunner

from pykmhelpers import KmindexRegistry
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.query import KmindexQuery


class ProjectShell:
    """Interactive shell for executing project-scoped commands."""

    def __init__(self, project_path: str, config: dict):
        """
        Initialize the project shell.

        Args:
            project_path: Path to the project directory
            config: Project configuration dictionary (k, z, s, version, etc.)
        """
        self.project_path = os.path.abspath(project_path)
        self.config = config
        self.project_name = os.path.basename(self.project_path)
        self.registry_path = os.path.join(self.project_path, "registry")

        # Create Click group for shell commands
        self.shell_commands = self._create_command_group()

    def _create_command_group(self) -> click.Group:
        """Create a Click group with all project-scoped commands."""
        @click.group(invoke_without_command=False)
        def shell():
            """Project shell commands."""
            pass

        @shell.command(name="info")
        def cmd_info():
            """Show project configuration and indices."""
            self._cmd_info()

        @shell.command(name="list")
        def cmd_list():
            """List all indices in the registry."""
            self._cmd_list()

        @shell.command(name="ls")
        def cmd_ls():
            """List all indices in the registry (alias for 'list')."""
            self._cmd_list()

        @shell.command(name="build")
        @click.argument("index_name")
        @click.option("--fof", required=True, type=click.Path(exists=True), help="Path to FOF file")
        @click.option("--bloom-size", required=True, type=int, help="Bloom filter size")
        @click.option("--threads", "-t", type=int, default=0, help="Number of threads")
        @click.option("--partitions", type=int, default=256, help="Number of partitions")
        @click.option("--assembled", is_flag=True, help="Mark as assembled data")
        @click.option("--force", "-f", is_flag=True, help="Skip confirmation")
        def cmd_build(index_name, fof, bloom_size, threads, partitions, assembled, force):
            """Build a new index."""
            self._cmd_build(index_name, fof, bloom_size, threads, partitions, assembled, force)

        @shell.command(name="query")
        @click.argument("index_name")
        @click.option("--query", "-q", required=True, type=click.Path(exists=True), help="Query file")
        @click.option("--output", "-o", default="query_results", help="Output directory")
        @click.option("--threads", "-t", type=int, default=1, help="Number of threads")
        @click.option("--aggregate", is_flag=True, help="Aggregate results")
        @click.option("--single-query", help="Single query identifier")
        def cmd_query(index_name, query, output, threads, aggregate, single_query):
            """Query an existing index."""
            self._cmd_query(index_name, query, output, threads, aggregate, single_query)

        return shell

    def run(self):
        """Start the interactive shell."""
        click.echo(f"\n✓ Entering project shell: {self.project_name}")
        click.echo(f"  Project path: {self.project_path}")
        click.echo(f"  K={self.config['k']}, Z={self.config['z']}, S={self.config['s']}")
        click.echo(f"\nType 'help' for available commands, 'exit' to quit.\n")

        while True:
            try:
                # Display prompt
                prompt = f"kmhelpers({self.project_name})> "
                user_input = input(prompt).strip()

                # Skip empty input
                if not user_input:
                    continue

                # Handle built-in commands
                if user_input == "exit" or user_input == "quit":
                    click.echo("Exiting project shell.")
                    break
                elif user_input == "help" or user_input.startswith("help "):
                    # Parse help command: "help" or "help <command>"
                    parts = user_input.split(maxsplit=1)
                    if len(parts) == 1:
                        # General help
                        self._show_help()
                    else:
                        # Help for specific command
                        command_name = parts[1]
                        self._show_command_help(command_name)
                else:
                    # Parse and execute Click command
                    self._execute_click_command(user_input)

            except KeyboardInterrupt:
                click.echo("\n\nInterrupted. Type 'exit' to quit.")
            except EOFError:
                click.echo()
                break
            except SystemExit:
                # Catch Click's sys.exit() calls
                pass
            except Exception as e:
                click.echo(f"Error: {e}", err=True)

    def _execute_click_command(self, user_input: str):
        """Parse and execute a Click command from user input."""
        try:
            # Parse the input into arguments
            args = shlex.split(user_input)
            if not args:
                return

            # Use Click's testing runner to execute the command
            runner = CliRunner()
            result = runner.invoke(self.shell_commands, args, catch_exceptions=False)

            # Print the output
            if result.output:
                click.echo(result.output, nl=False)

            # Check for errors
            if result.exit_code != 0 and result.exit_code != 2:  # 2 is Click's "help" exit code
                if result.exception:
                    click.echo(f"Error: {result.exception}", err=True)

        except click.ClickException as e:
            e.show()
        except Exception as e:
            click.echo(f"Error executing command: {e}", err=True)

    def _show_help(self):
        """Display available commands."""
        click.echo("\nAvailable commands:")
        click.echo("  info                          Show project configuration and indices")
        click.echo("  list, ls                      List all indices in the registry")
        click.echo("  build <name> --fof <file>    Build a new index")
        click.echo("    --bloom-size <size>         Required: bloom filter size (bits)")
        click.echo("    --threads <n>               Optional: number of threads (default: 0=auto)")
        click.echo("    --partitions <n>            Optional: number of partitions (default: 256)")
        click.echo("    --assembled                 Optional: mark as assembled data")
        click.echo("    --force / -f                Optional: skip confirmation")
        click.echo("  query <name> --query <file>  Query an existing index")
        click.echo("    --output <dir> / -o         Optional: output directory (default: query_results)")
        click.echo("    --threads <n> / -t          Optional: number of threads (default: 1)")
        click.echo("    --aggregate                 Optional: aggregate results")
        click.echo("    --single-query <name>       Optional: single query identifier")
        click.echo("  help [command]                Show help for all commands or a specific command")
        click.echo("  exit / quit                   Exit the shell\n")

    def _show_command_help(self, command_name: str):
        """Show detailed help for a specific command."""
        try:
            # Invoke the command with --help flag
            runner = CliRunner()
            result = runner.invoke(self.shell_commands, [command_name, "--help"])

            # Print the output
            if result.output:
                click.echo(result.output)
            else:
                click.echo(f"No help available for command: {command_name}", err=True)

        except Exception as e:
            click.echo(f"Error showing help: {e}", err=True)

    def _cmd_info(self):
        """Show project information."""
        click.echo(f"\nProject: {self.project_name}")
        click.echo(f"  Version: {self.config.get('version', 'unknown')}")
        click.echo(f"  Path: {self.config.get('path', self.project_path)}")
        click.echo(f"  Created: {self.config.get('date_creation', 'unknown')}")
        if self.config.get('description'):
            click.echo(f"  Description: {self.config['description']}")
        click.echo(f"  K-mer size (k): {self.config['k']}")
        click.echo(f"  Z offset (z): {self.config['z']}")
        click.echo(f"  Smer size (s): {self.config['s']}")
        click.echo()

        # Show directory structure
        click.echo("Project structure:")
        for subdir in ["registry", ".subindexes", "logs"]:
            dir_path = os.path.join(self.project_path, subdir)
            exists = "✓" if os.path.exists(dir_path) else "✗"
            click.echo(f"  {exists} {subdir}/")
        click.echo()

        # List indices in registry
        if os.path.exists(self.registry_path):
            try:
                registry = KmindexRegistry(self.registry_path)
                indices = registry.list_indices()

                if indices:
                    click.echo(f"Registered indices ({len(indices)}):")
                    for idx_name in indices:
                        index = registry.get_index(idx_name)
                        click.echo(f"  • {idx_name}")
                        click.echo(f"    Samples: {index.nb_samples}")
                        click.echo(f"    Partitions: {index.nb_partitions}")
                        click.echo(f"    K-mer: {index.kmer_size}")
                else:
                    click.echo("No indices registered yet.")
            except Exception as e:
                click.echo(f"Error reading registry: {e}", err=True)
        else:
            click.echo("Registry not yet created.")
        click.echo()

    def _cmd_list(self):
        """List all indices in the registry."""
        if not os.path.exists(self.registry_path):
            click.echo("No indices yet (registry not initialized).")
            return

        try:
            registry = KmindexRegistry(self.registry_path)
            indices = registry.list_indices()

            if not indices:
                click.echo("No indices in registry.")
                return

            click.echo(f"\nIndices in registry ({len(indices)} total):")
            for idx_name in indices:
                idx = registry.get_index(idx_name)
                click.echo(
                    f"  • {idx_name} ({idx.nb_samples} samples, "
                    f"{idx.nb_partitions} partitions, k={idx.kmer_size})"
                )
            click.echo()

        except Exception as e:
            click.echo(f"Error listing indices: {e}", err=True)

    def _cmd_build(self, index_name: str, fof: str, bloom_size: int, threads: int,
                   partitions: int, assembled: bool, force: bool):
        """Build an index."""
        try:
            # Validate FOF file
            if not os.path.isfile(fof):
                raise click.ClickException(f"FOF file not found: {fof}")

            # Load FOF file
            manager = FofManager()
            try:
                with open(fof, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            parts = line.split()
                            if len(parts) >= 2:
                                sample_name, file_path = parts[0], parts[1]
                                manager.add_sample(file_path, sample_name)
            except Exception as e:
                raise click.ClickException(f"Failed to load FOF file: {e}")

            click.echo(f"\nBuilding index: {index_name}")
            click.echo(f"  FOF file: {fof}")
            click.echo(f"  Samples: {manager.get_sample_count()}")
            click.echo(f"  Bloom size: {bloom_size}")
            click.echo(f"  Partitions: {partitions}")
            click.echo(f"  Threads: {threads if threads > 0 else 'auto'}")

            if not force and not click.confirm("Proceed with build?", default=True):
                click.echo("Build cancelled.")
                return

            # Create IndexBuilder
            builder = IndexBuilder(self.project_path, k=self.config["k"], z=self.config["z"])

            # Build the index
            index = builder.create_subindex(
                name=index_name,
                samples=manager,
                assembled=assembled,
                bloom_size=bloom_size,
                n_partitions=partitions,
                n_threads=threads,
                auto_check=True,
            )

            click.echo(f"\n✓ Index built successfully")
            click.echo(f"  Index name: {index_name}")
            click.echo(f"  Samples: {index.nb_samples}")
            click.echo(f"  Partitions: {index.nb_partitions}\n")

        except click.ClickException:
            raise
        except Exception as e:
            click.echo(f"Build failed: {e}", err=True)

    def _cmd_query(self, index_name: str, query: str, output: str, threads: int,
                   aggregate: bool, single_query: str | None):
        """Query an index."""
        try:
            # Validate query file
            if not os.path.isfile(query):
                raise click.ClickException(f"Query file not found: {query}")

            # Validate registry and index
            if not os.path.exists(self.registry_path):
                raise click.ClickException("Registry not found in project")

            registry = KmindexRegistry(self.registry_path)
            if not registry.has_index(index_name):
                raise click.ClickException(f"Index '{index_name}' not found in registry")

            click.echo(f"\nQuerying index: {index_name}")
            click.echo(f"  Query file: {query}")
            click.echo(f"  Output dir: {output}")
            click.echo(f"  Threads: {threads}")

            # Create output directory
            os.makedirs(output, exist_ok=True)

            # Initialize KmindexQuery
            kquery = KmindexQuery(query)

            # Execute query
            results = kquery.execute(
                registry_path=self.registry_path,
                output_dir=output,
                index_ids=[index_name],
                z=self.config["z"],
                single_query=single_query,
                aggregate=aggregate,
                threads=threads,
            )

            click.echo(f"\n✓ Query completed")
            click.echo(f"  Index: {index_name}")
            click.echo(f"  Results: {output}")
            click.echo(f"  Files found: {len(results)}\n")

        except click.ClickException:
            raise
        except Exception as e:
            click.echo(f"Query failed: {e}", err=True)