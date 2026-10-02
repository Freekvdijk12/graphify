"""A JS/TS line that opens with ``in``/``instanceof`` plus ``_``, ``$`` or a digit, after an unterminated line.

The pinned grammars read that prefix as the operator continuing the previous line, so the enclosing
type or class breaks; ``extract_js`` repairs the line before parsing without moving a byte or a line.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import graphify.extract as extract_module
from graphify.extract import extract_js

TS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")
JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs")

INTERFACE = (
    "export interface Media {\n"
    "  id: string\n"
    "  {name}: boolean\n"
    "  title: string\n"
    "}\n"
    "export function after(): void {}\n"
)
NESTED_TYPE_LITERAL = (
    "export interface Workspace {\n"
    "  meta: {\n"
    "    owner: string\n"
    "    {name}: boolean\n"
    "    size: number\n"
    "  }\n"
    "  title: string\n"
    "}\n"
    "export function after(): void {}\n"
)
TYPE_ALIAS = (
    "export type Media = {\n"
    "  id: string\n"
    "  {name}: number\n"
    "  title: string\n"
    "}\n"
    "export function after(): void {}\n"
)
CLASS_FIELD = (
    "class Box {\n"
    "  width = 1\n"
    "  {name} = 2\n"
    "  height = 3\n"
    "  area() { return this.width }\n"
    "}\n"
    "function after() { return new Box() }\n"
)
TAB_CLASS_FIELD = CLASS_FIELD.replace("  ", "\t")
STATEMENT = (
    "function grow() {\n"
    "  let width = 1\n"
    "  {name} = 2\n"
    "  return width\n"
    "}\n"
    "function after() { return grow() }\n"
)
CRLF_INTERFACE = INTERFACE.replace("\n", "\r\n")


def _source(template: str, name: str) -> str:
    return template.replace("{name}", name)


def _extract(path: Path, source: str) -> dict:
    path.write_bytes(source.encode("utf-8"))
    return extract_js(path)


def _labels(result: dict) -> set[str]:
    return {node["label"] for node in result["nodes"]}


def _id_form(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower())


@pytest.mark.parametrize("suffix", TS_SUFFIXES)
@pytest.mark.parametrize(
    "template, type_label",
    [
        pytest.param(INTERFACE, "Media", id="interface"),
        pytest.param(NESTED_TYPE_LITERAL, "Workspace", id="nested-object-type-literal"),
        pytest.param(TYPE_ALIAS, "Media", id="type-alias"),
    ],
)
def test_in_prefixed_member_after_unterminated_member_keeps_the_type_whole(
    tmp_path: Path, suffix: str, template: str, type_label: str
) -> None:
    """A semicolon-less ``in_*`` member leaves its type parsed whole and the file free of parse errors."""
    result = _extract(tmp_path / f"media{suffix}", _source(template, "in_stock"))

    assert "parse_errors" not in result, result.get("parse_errors")
    assert {type_label, "after()"} <= _labels(result)


@pytest.mark.parametrize("suffix", TS_SUFFIXES + JS_SUFFIXES)
def test_in_prefixed_class_field_parses_whole_in_js_and_ts(tmp_path: Path, suffix: str) -> None:
    """A semicolon-less ``in_*`` class field parses whole under every JavaScript and TypeScript suffix."""
    result = _extract(tmp_path / f"box{suffix}", _source(CLASS_FIELD, "in_box"))

    assert "parse_errors" not in result, result.get("parse_errors")
    assert {"Box", ".area()", "after()"} <= _labels(result)


@pytest.mark.parametrize(
    "suffix, template, name, twin",
    [
        pytest.param(".ts", INTERFACE, "in_stock", "on_stock", id="interface-underscore"),
        pytest.param(".tsx", NESTED_TYPE_LITERAL, "in_stock", "on_stock", id="nested-type-literal"),
        pytest.param(".mts", TYPE_ALIAS, "in$cart", "on$cart", id="type-alias-dollar"),
        pytest.param(".cts", INTERFACE, "in42", "on42", id="interface-digit"),
        pytest.param(".ts", INTERFACE, "instanceof_check", "onstanceof_check", id="instanceof-prefix"),
        pytest.param(".ts", CRLF_INTERFACE, "in_stock", "on_stock", id="crlf-interface"),
        pytest.param(".js", CLASS_FIELD, "in_box", "on_box", id="js-class-field"),
        pytest.param(".cjs", TAB_CLASS_FIELD, "in_box", "on_box", id="tab-indented-class-field"),
        pytest.param(".mjs", STATEMENT, "in_count", "on_count", id="js-statement"),
    ],
)
def test_in_prefixed_repair_is_the_same_as_a_renamed_twin(
    tmp_path: Path, suffix: str, template: str, name: str, twin: str
) -> None:
    """The repaired file extracts exactly as its same-length renamed twin does, modulo that one name."""
    path = tmp_path / f"subject{suffix}"
    twin_dump = json.dumps(_extract(path, _source(template, twin)), sort_keys=True)
    twin_as_subject = twin_dump.replace(twin, name).replace(_id_form(twin), _id_form(name))

    subject = _extract(path, _source(template, name))

    assert subject == json.loads(twin_as_subject)


@pytest.mark.parametrize(
    "suffix, source, stays_partial",
    [
        pytest.param(
            ".ts",
            "interface I {\n  a: number\n  inside: number\n  index: number\n"
            "  instance: number\n  is_x: number\n  b: string\n}\n",
            False,
            id="letter-after-in-and-is-prefix-ts",
        ),
        pytest.param(
            ".js",
            "class C {\n  a = 1\n  inside = 2\n  index = 3\n  instance = 4\n  is_x = 5\n}\n",
            False,
            id="letter-after-in-and-is-prefix-js",
        ),
        pytest.param(".ts", "interface I {\n  in_x: number\n  b: string\n}\n", False, id="first-member-ts"),
        pytest.param(".js", "class C {\n  in_x = 1\n  b = 2\n}\n", False, id="first-member-js"),
        pytest.param(
            ".ts", "interface I {\n  a: number;\n  in_x: number;\n  b: string;\n}\n", False,
            id="semicolon-separated-ts",
        ),
        pytest.param(".js", "class C {\n  a = 1;\n  in_x = 2;\n  b = 3;\n}\n", False, id="semicolon-separated-js"),
        pytest.param(
            ".ts", "type A = {\n  a: number,\n  in_x: number,\n  b: string,\n}\n", False,
            id="comma-separated-ts",
        ),
        pytest.param(".js", "const o = {\n  a: 1,\n  in_x: 2,\n}\n", False, id="comma-separated-js"),
        pytest.param(
            ".js", "const base = 1\nconst total = base +\n  in_rate * 2\n", False,
            id="genuine-continuation-js",
        ),
        pytest.param(".js", "let a = 1\nin_x = 2\nlet b = 3\n", True, id="no-indentation-js"),
        pytest.param(".ts", "let a = 1\nin_x = 2\nlet b = 3\n", True, id="no-indentation-ts"),
        pytest.param(
            ".js", "class C {\n  a = (1\n  in_x = 2\n  b = 3\n}\n", True,
            id="error-the-repair-cannot-clear-js",
        ),
        pytest.param(
            ".ts", "interface I {\n  a: (number\n  in_x: number\n  b: string\n}\n", True,
            id="error-the-repair-cannot-clear-ts",
        ),
    ],
)
def test_repair_leaves_every_control_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, source: str, stays_partial: bool
) -> None:
    """A control line reaches the parser byte for byte as written, and a file it cannot repair stays partial."""
    parsed: list[bytes] = []
    real_extract_generic = extract_module._extract_generic

    def recording_extract_generic(path, config, *, source_override=None):
        parsed.append(path.read_bytes() if source_override is None else source_override)
        return real_extract_generic(path, config, source_override=source_override)

    monkeypatch.setattr(extract_module, "_extract_generic", recording_extract_generic)

    result = _extract(tmp_path / f"control{suffix}", source)

    assert parsed == [source.encode("utf-8")]
    assert ("parse_errors" in result) == stays_partial, result.get("parse_errors")
