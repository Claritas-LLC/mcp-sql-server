import re

def is_valid_mermaid(diagram: str) -> bool:
    if not diagram or not isinstance(diagram, str):
        return False
    text = diagram.strip()
    # Basic sanity: Mermaid blocks typically start with a directive like 'erDiagram' or 'graph TD'
    if text.startswith("erDiagram"):
        return True
    if text.startswith("graph TD"):
        return True
    # Fallback: ensure parentheses/braces balance reasonably
    open_paren = diagram.count("[") + diagram.count("(")
    close_paren = diagram.count("]") + diagram.count(")")
    return open_paren == close_paren
