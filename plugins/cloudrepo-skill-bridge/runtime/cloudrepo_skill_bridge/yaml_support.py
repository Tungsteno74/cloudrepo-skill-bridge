"""Strict YAML mapping reader shared by skill resolution and package checks.

PyYAML is a declared runtime dependency, not a hidden optional parser.
Duplicate mapping keys are rejected rather than silently overwritten.
"""

from __future__ import annotations

from typing import Any, Dict

from .errors import BridgeError

try:
    import yaml
except ImportError:
    yaml = None


def load_mapping(source: str, error_code: str) -> Dict[str, Any]:
    """Parse one YAML mapping safely, preserving scalar types and explicit false."""
    if yaml is None:
        raise BridgeError(
            "YAML_PARSER_UNAVAILABLE",
            "PyYAML is required; install the declared runtime requirements",
        )

    class UniqueSafeLoader(yaml.SafeLoader):
        def construct_mapping(self, node: Any, deep: bool = False) -> Dict[str, Any]:
            if not isinstance(node, yaml.MappingNode):
                raise yaml.constructor.ConstructorError(
                    None, None, "Expected a YAML mapping", node.start_mark
                )
            result: Dict[str, Any] = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str):
                    raise yaml.constructor.ConstructorError(
                        None, None, "Mapping keys must be strings", key_node.start_mark
                    )
                if key in result:
                    raise yaml.constructor.ConstructorError(
                        None, None, "Duplicate YAML mapping key", key_node.start_mark
                    )
                result[key] = self.construct_object(value_node, deep=deep)
            return result

    try:
        value = yaml.load(source, Loader=UniqueSafeLoader)
    except yaml.YAMLError as exc:
        raise BridgeError(error_code, "Malformed or ambiguous YAML mapping") from exc
    if not isinstance(value, dict):
        raise BridgeError(error_code, "Expected a YAML mapping")
    return value
