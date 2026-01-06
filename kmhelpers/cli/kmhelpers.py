import sys
import os
import click
from pathlib import Path

@click.group()
def cli():
    """A pipeable CLI tool."""
    pass

def get_input(input_file):
    """Return input from file or stdin."""
    if input_file:
        return open(input_file)
    if not sys.stdin.isatty():
        return sys.stdin
    return None

@cli.command()
@click.option('-i', '--input', 'input_file', type=click.Path(exists=True))
@click.option('-n', '--number', default=1, type=int)
def command_1(input_file, number):
    """Process and output to stdout."""
    stream = get_input(input_file)
    if not stream:
        raise click.UsageError("No input provided")
    
    for line in stream:
        # your processing here
        click.echo(f"{number}: {line.rstrip()}")
    
    if input_file:
        stream.close()

@cli.command()
@click.option('-i', '--input', 'input_file', type=click.Path(exists=True))
@click.option('--upper', is_flag=True)
def command_2(input_file, upper):
    """Another processing step."""
    stream = get_input(input_file)
    if not stream:
        raise click.UsageError("No input provided")
    
    for line in stream:
        out = line.rstrip()
        if upper:
            out = out.upper()
        click.echo(out)
    
    if input_file:
        stream.close()

@cli.command()
def install_completion():
    """Install shell completion."""
    shell = os.environ.get('SHELL', '')
    home = Path.home()
    
    if 'zsh' in shell:
        comp_file = home / '.mytool-complete.zsh'
        rc_file = home / '.zshrc'
        source_line = f'source {comp_file}'
        env_var = 'zsh_source'
    elif 'bash' in shell:
        comp_file = home / '.mytool-complete.bash'
        rc_file = home / '.bashrc'
        source_line = f'source {comp_file}'
        env_var = 'bash_source'
    else:
        click.echo(f"Unsupported shell: {shell}", err=True)
        return 1
    
    # Generate completion script
    import subprocess
    env = os.environ.copy()
    env['_MYTOOL_COMPLETE'] = env_var
    result = subprocess.run(['mytool'], env=env, capture_output=True, text=True)
    comp_file.write_text(result.stdout)
    click.echo(f"Generated {comp_file}")
    
    # Add to rc file if not present
    rc_content = rc_file.read_text() if rc_file.exists() else ''
    if source_line not in rc_content:
        with open(rc_file, 'a') as f:
            f.write(f'\n# mytool completion\n{source_line}\n')
        click.echo(f"Added source line to {rc_file}")
    else:
        click.echo(f"Already in {rc_file}")
    
    click.echo("Restart your shell or run: " + source_line)

if __name__ == '__main__':
    cli()
