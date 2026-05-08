"""Language registry — Python + JS + TS specs only (Aura MVP).

Single source of truth for extension/filename → language tag mapping
and per-language metadata. Trimmed lift from repowise (AGPL-3.0).
"""

from __future__ import annotations

from collections.abc import Iterable

from .spec import LanguageSpec


_SPECS: tuple[LanguageSpec, ...] = (
    LanguageSpec(
        tag="python",
        display_name="Python",
        extensions=frozenset({".py", ".pyi"}),
        grammar_package="tree_sitter_python",
        scm_file="python.scm",
        heritage_node_types=frozenset({"class_definition"}),
        entry_point_patterns=(
            "main.py",
            "app.py",
            "__main__.py",
            "manage.py",
            "wsgi.py",
            "asgi.py",
        ),
        manifest_files=("pyproject.toml", "setup.py", "setup.cfg"),
        lock_files=("poetry.lock", "uv.lock"),
        generated_suffixes=("_pb2.py", "_pb2_grpc.py"),
        shebang_tokens=("python",),
        blocked_dirs=(
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            ".eggs",
            "site-packages",
            ".venv",
            "venv",
        ),
        blocked_extensions=(".pyc", ".pyo", ".pyd"),
        builtin_calls=frozenset(
            {
                "abs", "all", "any", "ascii", "bin", "bool", "bytearray",
                "bytes", "callable", "chr", "classmethod", "compile",
                "complex", "delattr", "dict", "dir", "divmod", "enumerate",
                "eval", "exec", "filter", "float", "format", "frozenset",
                "getattr", "globals", "hasattr", "hash", "help", "hex", "id",
                "input", "int", "isinstance", "issubclass", "iter", "len",
                "list", "locals", "map", "max", "memoryview", "min", "next",
                "object", "oct", "open", "ord", "pow", "print", "property",
                "range", "repr", "reversed", "round", "set", "setattr",
                "slice", "sorted", "staticmethod", "str", "sum", "super",
                "tuple", "type", "vars", "zip", "__import__",
            }
        ),
        builtin_parents=frozenset(
            {
                "object", "Exception", "BaseException", "type", "ABC",
                "ABCMeta", "Protocol", "NamedTuple", "TypedDict", "Enum",
                "IntEnum", "Flag", "IntFlag",
            }
        ),
        color_hex="#3572A5",
    ),
    LanguageSpec(
        tag="typescript",
        display_name="TypeScript",
        extensions=frozenset({".ts", ".tsx"}),
        grammar_package="tree_sitter_typescript",
        grammar_loader="language_typescript",
        scm_file="typescript.scm",
        heritage_node_types=frozenset(
            {"class_declaration", "abstract_class_declaration", "interface_declaration"}
        ),
        entry_point_patterns=("index.ts", "main.ts", "app.ts", "server.ts"),
        manifest_files=("package.json",),
        lock_files=("package-lock.json", "yarn.lock", "pnpm-lock.yaml"),
        generated_suffixes=("_pb.ts",),
        blocked_dirs=("node_modules", ".next", "dist", "build", ".turbo"),
        builtin_calls=frozenset(
            {
                "parseInt", "parseFloat", "isNaN", "isFinite", "decodeURI",
                "decodeURIComponent", "encodeURI", "encodeURIComponent",
                "setTimeout", "setInterval", "clearTimeout", "clearInterval",
                "fetch", "require", "eval", "atob", "btoa", "JSON", "Math",
                "console", "Reflect", "Proxy", "Object", "Array", "String",
                "Number", "Boolean", "Date", "RegExp", "Promise", "Set", "Map",
                "WeakMap", "WeakSet", "Symbol", "ArrayBuffer", "DataView",
                "Uint8Array", "Error", "TypeError", "RangeError",
                "SyntaxError", "ReferenceError", "Int8Array", "Int16Array",
                "Int32Array", "Float32Array", "Float64Array",
            }
        ),
        builtin_parents=frozenset({"Error", "Object"}),
        color_hex="#3178C6",
    ),
    LanguageSpec(
        tag="javascript",
        display_name="JavaScript",
        extensions=frozenset({".js", ".jsx", ".mjs", ".cjs"}),
        grammar_package="tree_sitter_javascript",
        scm_file="javascript.scm",
        heritage_node_types=frozenset({"class_declaration"}),
        entry_point_patterns=("index.js", "main.js", "app.js", "server.js"),
        manifest_files=("package.json",),
        lock_files=("package-lock.json", "yarn.lock", "pnpm-lock.yaml"),
        generated_suffixes=("_pb.js",),
        shebang_tokens=("node",),
        blocked_dirs=("node_modules", "dist", "build", ".turbo"),
        builtin_calls=frozenset(
            {
                "parseInt", "parseFloat", "isNaN", "isFinite", "decodeURI",
                "decodeURIComponent", "encodeURI", "encodeURIComponent",
                "setTimeout", "setInterval", "clearTimeout", "clearInterval",
                "fetch", "require", "eval", "atob", "btoa", "JSON", "Math",
                "console", "Reflect", "Proxy", "Object", "Array", "String",
                "Number", "Boolean", "Date", "RegExp", "Promise", "Set", "Map",
                "WeakMap", "WeakSet", "Symbol", "ArrayBuffer", "DataView",
                "Uint8Array", "Error", "TypeError", "RangeError",
                "SyntaxError", "ReferenceError", "Int8Array", "Int16Array",
                "Int32Array", "Float32Array", "Float64Array",
            }
        ),
        builtin_parents=frozenset({"Error", "Object"}),
        color_hex="#F1E05A",
    ),
)


class LanguageRegistry:
    """Central registry.  All language-specific lookups go through here."""

    __slots__ = ("_ext_map", "_filename_map", "_specs")

    def __init__(self, specs: tuple[LanguageSpec, ...] = _SPECS) -> None:
        self._specs: dict[str, LanguageSpec] = {s.tag: s for s in specs}

        self._ext_map: dict[str, str] = {}
        for spec in specs:
            for ext in spec.extensions:
                if ext not in self._ext_map:
                    self._ext_map[ext] = spec.tag

        self._filename_map: dict[str, str] = {}
        for spec in specs:
            for fn in spec.special_filenames:
                if fn not in self._filename_map:
                    self._filename_map[fn] = spec.tag

    def get(self, tag: str) -> LanguageSpec | None:
        return self._specs.get(tag)

    def from_extension(self, ext: str) -> str:
        return self._ext_map.get(ext, "unknown")

    def from_filename(self, name: str) -> str | None:
        return self._filename_map.get(name)

    def all_extensions(self) -> dict[str, str]:
        return dict(self._ext_map)

    def all_special_filenames(self) -> dict[str, str]:
        return dict(self._filename_map)

    def all_code_extensions(self) -> frozenset[str]:
        return frozenset(
            ext for spec in self._specs.values() if spec.is_code for ext in spec.extensions
        )

    def code_languages(self) -> frozenset[str]:
        return frozenset(
            s.tag for s in self._specs.values() if s.is_code and not s.is_passthrough
        )

    def config_languages(self) -> frozenset[str]:
        return frozenset(s.tag for s in self._specs.values() if not s.is_code)

    def passthrough_languages(self) -> frozenset[str]:
        return frozenset(s.tag for s in self._specs.values() if s.is_passthrough)

    def infra_languages(self) -> frozenset[str]:
        return frozenset(s.tag for s in self._specs.values() if s.is_infra)

    def entry_point_names(self) -> frozenset[str]:
        return frozenset(p for s in self._specs.values() for p in s.entry_point_patterns)

    def manifest_filenames(self) -> frozenset[str]:
        return frozenset(f for s in self._specs.values() for f in s.manifest_files)

    def blocked_dirs(self) -> frozenset[str]:
        return frozenset(d for s in self._specs.values() for d in s.blocked_dirs)

    def generated_suffixes(self) -> frozenset[str]:
        return frozenset(sf for s in self._specs.values() for sf in s.generated_suffixes)

    def extensions_for(self, tags: Iterable[str]) -> frozenset[str]:
        tag_set = set(tags)
        return frozenset(
            ext for spec in self._specs.values() if spec.tag in tag_set for ext in spec.extensions
        )

    def all_specs(self) -> list[LanguageSpec]:
        return list(self._specs.values())


REGISTRY = LanguageRegistry()
