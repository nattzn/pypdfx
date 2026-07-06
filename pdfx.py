#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader, PdfWriter


VERSION = "0.1.0"

COMMAND_ALIASES = {
    "pick": "pick",
    "extract": "pick",
    "drop": "drop",
    "delete": "drop",
    "remove": "drop",
    "merge": "merge",
    "append": "merge",
    "out": "out",
    "output": "out",
}
COMMANDS = set(COMMAND_ALIASES)


class UsageError(Exception):
    pass


@dataclass(frozen=True)
class PageRef:
    index: int       # zero-based page index
    rotation: int    # clockwise degrees: 0, 90, 180, 270


@dataclass(frozen=True)
class Action:
    command: str
    input_path: str | None = None
    input_paths: tuple[str, ...] = ()
    page_spec: str | None = None


@dataclass(frozen=True)
class ParsedCommand:
    actions: tuple[Action, ...]
    output_path: str


def usage() -> str:
    return f"""pdfx {VERSION}

Usage:
  pdfx --version
  pdfx pick INPUT.pdf [PAGE_SPEC] out OUTPUT.pdf
  pdfx pick INPUT.pdf [PAGE_SPEC] drop INPUT2.pdf [PAGE_SPEC] out OUTPUT.pdf
  pdfx drop INPUT.pdf [PAGE_SPEC] out OUTPUT.pdf
  pdfx merge INPUT1.pdf INPUT2.pdf [...] out OUTPUT.pdf
  pdfx merge INPUT1.pdf INPUT2.pdf [...] drop INPUT3.pdf [PAGE_SPEC] out OUTPUT.pdf

Recommended commands:
  pick   INPUT.pdf [PAGE_SPEC]  add selected pages in the specified order;
                                when PAGE_SPEC is omitted, add all pages
  drop   INPUT.pdf [PAGE_SPEC]  add all pages except the specified pages;
                                when all pages are dropped, this command is skipped
  merge  INPUT.pdf [...]        add all pages from each PDF; no page spec
  out    OUTPUT.pdf             output path; must be the final command

Aliases:
  extract -> pick, delete/remove -> drop, append -> merge, output -> out

PAGE_SPEC examples:
  omitted           all pages
  "1,2,3"           pages 1, 2, 3
  "1, 3 - 5"        spaces are ignored; same as 1,3-5
  "1,1,1"           duplicate pages are allowed
  "3,2,1"           order is preserved
  "-1"              last page
  "8--1" or "8-"    page 8 through the last page
  "1-4R"            pages 1 through 4 rotated right
  "R"               all pages rotated right
  "L"               all pages rotated left
  "RR" or "LL"      all pages rotated 180 degrees
  "1,RR,3"          page 1, then all pages rotated 180 degrees, then page 3
  "1L,2R,3rr"       rotate each selected page; case-insensitive
"""


def normalize_command(token: str) -> str | None:
    return COMMAND_ALIASES.get(token.lower())


def is_command(token: str) -> bool:
    return token.lower() in COMMANDS


def parse_argv(argv: list[str]) -> ParsedCommand:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        raise UsageError(usage())

    actions: list[Action] = []
    output_path: str | None = None
    i = 0

    while i < len(argv):
        raw = argv[i]
        command = normalize_command(raw)
        if command is None:
            raise UsageError(f"Unknown command: {raw}\n\n{usage()}")
        i += 1

        if command == "out":
            if i >= len(argv):
                raise UsageError("out requires an output path")
            output_path = argv[i]
            i += 1
            if i != len(argv):
                raise UsageError("out must be the final command")
            break

        if command in {"pick", "drop"}:
            if i >= len(argv):
                raise UsageError(f"{command} requires an input PDF path")
            input_path = argv[i]
            i += 1

            spec_tokens: list[str] = []
            while i < len(argv) and not is_command(argv[i]):
                spec_tokens.append(argv[i])
                i += 1
            page_spec = "".join(spec_tokens) if spec_tokens else None
            actions.append(Action(command=command, input_path=input_path, page_spec=page_spec))
            continue

        if command == "merge":
            paths: list[str] = []
            while i < len(argv) and not is_command(argv[i]):
                paths.append(argv[i])
                i += 1
            if not paths:
                raise UsageError("merge requires at least one input PDF path")
            actions.append(Action(command=command, input_paths=tuple(paths)))
            continue

        raise AssertionError(f"unhandled command: {command}")

    if not actions:
        raise UsageError("No input action was specified\n\n" + usage())
    if output_path is None:
        raise UsageError("Missing output command: out OUTPUT.pdf")
    return ParsedCommand(actions=tuple(actions), output_path=output_path)


def parse_rotation_suffix(token: str) -> tuple[str, int]:
    token = token.strip()
    suffix_match = re.search(r"[lLrR]+$", token)
    if not suffix_match:
        return token, 0

    suffix = suffix_match.group(0).upper()
    base = token[: suffix_match.start()]
    if len(suffix) > 2:
        raise UsageError(f"Rotation suffix must be L, R, LL, or RR: {token}")
    if len(set(suffix)) != 1:
        raise UsageError(f"Do not mix L and R in one page token: {token}")

    if suffix == "L":
        return base, 270
    if suffix == "R":
        return base, 90
    return base, 180


def resolve_page_number(value: int, page_count: int, original: str) -> int:
    if value == 0:
        raise UsageError(f"Page number 0 is invalid: {original}")
    index = value - 1 if value > 0 else page_count + value
    if index < 0 or index >= page_count:
        raise UsageError(
            f"Page number out of range: {original} "
            f"(this PDF has {page_count} pages)"
        )
    return index


def expand_page_base(base: str, page_count: int, original: str) -> list[int]:
    if base == "":
        return list(range(page_count))

    if base == "*":
        raise UsageError("* is no longer supported; omit PAGE_SPEC or the page number instead")

    if re.fullmatch(r"-?\d+", base):
        return [resolve_page_number(int(base), page_count, original)]

    match = re.fullmatch(r"(-?\d+)-(-?\d+)?", base)
    if match:
        start_num = int(match.group(1))
        end_text = match.group(2)
        start = resolve_page_number(start_num, page_count, original)
        end = page_count - 1 if end_text is None else resolve_page_number(int(end_text), page_count, original)
        step = 1 if start <= end else -1
        return list(range(start, end + step, step))

    raise UsageError(f"Invalid page spec token: {original}")


def parse_page_spec(spec: str | None, page_count: int) -> list[PageRef]:
    compact = "" if spec is None else re.sub(r"\s+", "", spec)
    if compact == "":
        return [PageRef(index=index, rotation=0) for index in range(page_count)]

    result: list[PageRef] = []
    for token in compact.split(","):
        if token == "":
            raise UsageError(f"Invalid PAGE_SPEC: {spec}")
        base, rotation = parse_rotation_suffix(token)
        for index in expand_page_base(base, page_count, token):
            result.append(PageRef(index=index, rotation=rotation))
    return result


def add_pick(writer: PdfWriter, reader: PdfReader, page_spec: str | None) -> int:
    refs = parse_page_spec(page_spec, len(reader.pages))
    for ref in refs:
        added = writer.add_page(reader.pages[ref.index])
        if ref.rotation:
            added.rotate(ref.rotation)
    return len(refs)


def add_drop(writer: PdfWriter, reader: PdfReader, page_spec: str | None, input_path: str) -> int:
    refs = parse_page_spec(page_spec, len(reader.pages))
    rotated_refs = [ref for ref in refs if ref.rotation]
    if rotated_refs:
        raise UsageError("drop does not accept rotation suffixes; use pick when rotation is needed")

    drop_indexes = {ref.index for ref in refs}
    if len(reader.pages) > 0 and len(drop_indexes) == len(reader.pages):
        spec_label = page_spec if page_spec not in {None, ""} else "all pages"
        print(f"skipped: drop {input_path} {spec_label} would remove all pages")
        return 0

    added_count = 0
    for index, page in enumerate(reader.pages):
        if index not in drop_indexes:
            writer.add_page(page)
            added_count += 1
    return added_count


def add_merge(writer: PdfWriter, readers: Iterable[PdfReader]) -> int:
    added_count = 0
    for reader in readers:
        for page in reader.pages:
            writer.add_page(page)
            added_count += 1
    return added_count


def run(parsed: ParsedCommand) -> None:
    writer = PdfWriter()
    readers: list[PdfReader] = []  # keep readers alive until writer.write() completes

    for action in parsed.actions:
        if action.command == "pick":
            assert action.input_path is not None
            reader = PdfReader(action.input_path)
            readers.append(reader)
            add_pick(writer, reader, action.page_spec)

        elif action.command == "drop":
            assert action.input_path is not None
            reader = PdfReader(action.input_path)
            readers.append(reader)
            add_drop(writer, reader, action.page_spec, action.input_path)

        elif action.command == "merge":
            action_readers: list[PdfReader] = []
            for input_path in action.input_paths:
                reader = PdfReader(input_path)
                readers.append(reader)
                action_readers.append(reader)
            add_merge(writer, action_readers)

        else:
            raise AssertionError(f"unhandled action: {action.command}")

    if len(writer.pages) == 0:
        raise UsageError("The output would contain 0 pages; nothing was written")

    output = Path(parsed.output_path)
    if output.parent != Path(""):
        output.parent.mkdir(parents=True, exist_ok=True)
    writer.write(str(output))


def main(argv: list[str]) -> int:
    if argv and argv[0] in {"-v", "--version", "version"}:
        print(f"pdfx {VERSION}")
        return 0
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(usage())
        return 0

    try:
        parsed = parse_argv(argv)
        run(parsed)
        print(f"wrote: {parsed.output_path}")
        return 0
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"file not found: {exc.filename}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
