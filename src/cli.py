import typer

##########
# public #
##########


def run_cli() -> None:
    cli = _init_cli()
    cli()


###########
# private #
###########


def _init_cli() -> typer.Typer:
    """
    Initialize the CLI application with commands.

    Returns
    -------
    typer.Typer
        Configured Typer CLI object with registered commands
    """
    cli = typer.Typer(
        context_settings={"help_option_names": ["-h", "--help"]},
        pretty_exceptions_enable=False,
        pretty_exceptions_show_locals=False,
    )
    cli.command("run")(_run)
    cli.command("r", hidden=True)(_run)
    return cli


def _run() -> None:
    pass
