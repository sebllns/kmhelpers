import sys
import click

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

if __name__ == '__main__':
    cli()
