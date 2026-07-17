"""Shell completion scripts for bash, zsh, and fish."""
from textwrap import dedent

BASH_COMPLETION = dedent("""\
    # Tokenade bash completion
    _tokenade_completions() {
        local cur prev commands
        COMPREPLY=()
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        commands="config run test fingerprint validate export load encrypt decrypt rekey health sessions plugin completion cloak launch refresh-browser recommend"

        if [[ ${cur} == -* ]]; then
            COMPREPLY=( $(compgen -W "--help --version --browser-name --domains --output --port --host --visible --session --format --password --expiry --profile --site-config --list-profiles" -- ${cur}) )
        else
            COMPREPLY=( $(compgen -W "${commands}" -- ${cur}) )
        fi
        return 0
    }
    complete -F _tokenade_completions tokenade
""")

ZSH_COMPLETION = dedent("""\
    #compdef tokenade
    # Tokenade zsh completion

    _tokenade() {
        _arguments \
            '1:command:(config run test fingerprint validate export load encrypt decrypt rekey health sessions plugin completion cloak launch refresh-browser recommend)' \
            '*::arg:->args'
    }

    _tokenade "$@"
""")

FISH_COMPLETION = dedent("""\
    # Tokenade fish completion
    complete -c tokenade -f
    complete -c tokenade -n '__fish_use_subcommand' -a config -d 'Manage configuration'
    complete -c tokenade -n '__fish_use_subcommand' -a run -d 'Run executable plugin'
    complete -c tokenade -n '__fish_use_subcommand' -a test -d 'Test portability'
    complete -c tokenade -n '__fish_use_subcommand' -a fingerprint -d 'Manage fingerprints'
    complete -c tokenade -n '__fish_use_subcommand' -a validate -d 'Validate sessions'
    complete -c tokenade -n '__fish_use_subcommand' -a export -d 'Export session'
    complete -c tokenade -n '__fish_use_subcommand' -a load -d 'Load session'
    complete -c tokenade -n '__fish_use_subcommand' -a encrypt -d 'Encrypt session'
    complete -c tokenade -n '__fish_use_subcommand' -a decrypt -d 'Decrypt session'
    complete -c tokenade -n '__fish_use_subcommand' -a rekey -d 'Change encryption password'
    complete -c tokenade -n '__fish_use_subcommand' -a health -d 'Check session health'
    complete -c tokenade -n '__fish_use_subcommand' -a sessions -d 'Manage sessions'
    complete -c tokenade -n '__fish_use_subcommand' -a plugin -d 'Manage plugins'
    complete -c tokenade -n '__fish_use_subcommand' -a completion -d 'Generate completions'
    complete -c tokenade -n '__fish_use_subcommand' -a cloak -d 'CloakBrowser management'
    complete -c tokenade -n '__fish_use_subcommand' -a launch -d 'Launch browser'
    complete -c tokenade -n '__fish_use_subcommand' -a refresh-browser -d 'Refresh through browser'
    complete -c tokenade -n '__fish_use_subcommand' -a recommend -d 'Recommend handler'
""")


def install_completion(shell: str = "bash"):
    """Install shell completion."""
    from pathlib import Path

    if shell == "bash":
        comp_dir = Path.home() / ".bash_completion.d"
        comp_dir.mkdir(exist_ok=True)
        comp_file = comp_dir / "tokenade"
        comp_file.write_text(BASH_COMPLETION)
        print(f"Installed bash completion to {comp_file}")
        print("Restart your shell or run: source ~/.bash_completion.d/tokenade")
    elif shell == "zsh":
        comp_dir = Path.home() / ".zsh" / "completions"
        comp_dir.mkdir(parents=True, exist_ok=True)
        comp_file = comp_dir / "_tokenade"
        comp_file.write_text(ZSH_COMPLETION)
        print(f"Installed zsh completion to {comp_file}")
    elif shell == "fish":
        comp_dir = Path.home() / ".config" / "fish" / "completions"
        comp_dir.mkdir(parents=True, exist_ok=True)
        comp_file = comp_dir / "tokenade.fish"
        comp_file.write_text(FISH_COMPLETION)
        print(f"Installed fish completion to {comp_file}")
