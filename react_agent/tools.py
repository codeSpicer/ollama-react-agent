import ast
import html
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

WORKDIR = Path(os.environ.get("AGENT_WORKDIR", Path.cwd() / "workdir"))

MAX_READ_CHARS = 20000


def _resolve(path):
    target = (WORKDIR / path).resolve()
    root = WORKDIR.resolve()
    if target != root and root not in target.parents:
        return None, (
            f"ERROR: path escapes workdir: {path} — "
            "use a path relative to the workdir, e.g. 'NOTES.md'."
        )
    return target, None


def calculator(expression):
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return (
            f"ERROR: could not parse {expression!r} — "
            "use plain arithmetic with digits, e.g. '17 * 23'."
        )
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.Pow,
        ast.UAdd,
        ast.USub,
        ast.Load,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            return (
                f"ERROR: unsupported expression {expression!r} — "
                "use numbers with + - * / % ** and parentheses only."
            )
        if isinstance(node, ast.Constant) and not isinstance(
            node.value, (int, float)
        ):
            return (
                f"ERROR: unsupported value {node.value!r} — "
                "spell out words as digits first, e.g. 'twelve' -> 12."
            )
    try:
        return str(
            eval(compile(tree, "<calculator>", "eval"), {"__builtins__": {}}, {})
        )
    except ZeroDivisionError:
        return "ERROR: division by zero — check the divisor and retry."
    except Exception as exc:
        return f"ERROR: could not evaluate {expression!r} ({exc}) — retry."


def read_file(path):
    target, err = _resolve(path)
    if err:
        return err
    if not target.is_file():
        try:
            available = sorted(p.name for p in WORKDIR.iterdir() if p.is_file())
        except FileNotFoundError:
            available = []
        hint = (
            f"available files: {', '.join(available)}"
            if available
            else "workdir is empty"
        )
        return f"ERROR: file not found: {path} — {hint}."
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"ERROR: {path} is not UTF-8 text — this tool reads text files only."
    except OSError as exc:
        return f"ERROR: could not read {path} ({exc}) — check the path and retry."
    if len(text) > MAX_READ_CHARS:
        text = text[:MAX_READ_CHARS] + f"\n...[truncated at {MAX_READ_CHARS} chars]"
    return text


def write_file(path, content):
    target, err = _resolve(path)
    if err:
        return err
    if not isinstance(content, str):
        return "ERROR: content must be a string — pass the file body as text."
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"ERROR: could not write {path} ({exc}) — check the path and retry."
    return f"Wrote {len(content)} chars to {path}."


def _ddg_link(raw):
    raw = html.unescape(raw)
    if raw.startswith("//duckduckgo.com/l/"):
        qs = parse_qs(urlparse("https:" + raw).query)
        raw = unquote(qs.get("uddg", [raw])[0])
    return raw


def web_search(query, count=3):
    if not query or not str(query).strip():
        return "ERROR: empty query — provide a search query string."
    count = max(1, min(int(count), 5))
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return f"ERROR: web search failed ({exc}) — check network and retry."
    page = resp.text
    links = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        page,
        re.DOTALL,
    )
    snippets = re.findall(
        r'class="result__snippet"[^>]*>(.*?)</a>', page, re.DOTALL
    )
    results = []
    for i, (raw_url, raw_title) in enumerate(links[:count]):
        title = re.sub(r"<[^>]+>", "", raw_title).strip()
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
        results.append(f"{i + 1}. {html.unescape(title)} — {_ddg_link(raw_url)}\n   {html.unescape(snippet)}")
    if not results:
        return (
            f"ERROR: no results for {query!r} — "
            "try different keywords or check network."
        )
    return "\n".join(results)


def get_weather(latitude, longitude):
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return (
            "ERROR: latitude/longitude must be numbers — "
            "e.g. latitude 52.52, longitude 13.41 for Berlin."
        )
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return (
            "ERROR: coordinates out of range — "
            "latitude -90..90, longitude -180..180."
        )
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
        current = resp.json().get("current_weather", {})
    except requests.RequestException as exc:
        return f"ERROR: weather request failed ({exc}) — check network and retry."
    except ValueError:
        return "ERROR: weather service returned bad data — retry."
    if not current:
        return "ERROR: no current weather in response — retry."
    return (
        f"{current.get('temperature')}°C, wind {current.get('windspeed')} km/h, "
        f"code {current.get('weathercode')} at {current.get('time')} "
        f"(lat {lat}, lon {lon})."
    )


def _schema(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


CALCULATOR_SCHEMA = _schema(
    "calculator",
    "Evaluates a plain arithmetic expression with digits and + - * / % **. "
    "Use when the task asks for a numeric computation. "
    "Pass digits only — spell out words as numbers first.",
    {"expression": {"type": "string", "description": "Arithmetic expression, e.g. '17 * 23'."}},
    ["expression"],
)

READ_FILE_SCHEMA = _schema(
    "read_file",
    "Reads a UTF-8 text file under the workdir. "
    "Use when the task references a local file by name. "
    "Returns file contents, or an ERROR listing available files on a miss.",
    {"path": {"type": "string", "description": "Path relative to the workdir, e.g. 'NOTES.md'."}},
    ["path"],
)

WRITE_FILE_SCHEMA = _schema(
    "write_file",
    "Writes text to a file under the workdir, creating parent dirs. "
    "Use when the task asks to save, store, or persist content to a file.",
    {
        "path": {"type": "string", "description": "Path relative to the workdir, e.g. 'out.md'."},
        "content": {"type": "string", "description": "Full text body to write."},
    },
    ["path", "content"],
)

WEB_SEARCH_SCHEMA = _schema(
    "web_search",
    "Searches the public web via DuckDuckGo and returns top snippets with URLs. "
    "Use when the task needs information not present locally. "
    "Do not use for local files, arithmetic, or creative writing.",
    {
        "query": {"type": "string", "description": "Search query keywords."},
        "count": {"type": "integer", "description": "How many results (1-5, default 3)."},
    },
    ["query"],
)

GET_WEATHER_SCHEMA = _schema(
    "get_weather",
    "Returns current weather for numeric coordinates via Open-Meteo. "
    "Use when the task asks about weather at a place — geocode the place "
    "to latitude/longitude first, then call with numbers.",
    {
        "latitude": {"type": "number", "description": "Latitude -90..90, e.g. 52.52."},
        "longitude": {"type": "number", "description": "Longitude -180..180, e.g. 13.41."},
    },
    ["latitude", "longitude"],
)

TOOLS = [
    CALCULATOR_SCHEMA,
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    WEB_SEARCH_SCHEMA,
    GET_WEATHER_SCHEMA,
]

HANDLERS = {
    "calculator": calculator,
    "read_file": read_file,
    "write_file": write_file,
    "web_search": web_search,
    "get_weather": get_weather,
}

REGISTRY = {
    name: {"schema": schema, "handler": HANDLERS[name]}
    for schema in TOOLS
    for name in [schema["function"]["name"]]
}


def dispatch(name, arguments):
    entry = REGISTRY.get(name)
    if entry is None:
        return (
            f"ERROR: unknown tool {name!r} — "
            f"available: {', '.join(sorted(REGISTRY))}."
        )
    if not isinstance(arguments, dict):
        return (
            f"ERROR: args for {name} must be an object — "
            f"got {type(arguments).__name__}."
        )
    try:
        return str(entry["handler"](**arguments))
    except TypeError as exc:
        return (
            f"ERROR: bad args for {name} ({exc}) — "
            "check required parameters and retry."
        )
    except Exception as exc:
        return f"ERROR: {name} failed ({exc}) — retry with corrected args."
