try:
    from rich.console import Console
    from rich.markdown import Markdown
except Exception:  # pragma: no cover
    Console = None
    Markdown = None


def print_final_output(text: str, render_markdown: bool = True) -> None:
    if not render_markdown:
        print(text)
        return
    if Console is None or Markdown is None:
        print(text)
        return
    console = Console()
    console.print(Markdown(text))
