#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""Jinja2 template rendering context helper."""

import contextlib
import warnings
from typing import Any, Container, Dict, Iterable, Iterator, List, MutableMapping, Tuple

_NOT_SET: Any = object()


class VariableAccessor:
    """Wrapper to access Variable values in template."""

    def __init__(self, *, deserialize_json: bool) -> None:
        self._deserialize_json = deserialize_json
        self.var: Any = None

    def __getattr__(self, key: str) -> Any:
        from airflow.models.variable import Variable

        self.var = Variable.get(key, deserialize_json=self._deserialize_json)
        return self.var

    def __repr__(self) -> str:
        return str(self.var)

    def get(self, key, default: Any = _NOT_SET) -> Any:
        from airflow.models.variable import Variable

        if default is _NOT_SET:
            return Variable.get(key, deserialize_json=self._deserialize_json)
        return Variable.get(key, default, deserialize_json=self._deserialize_json)


class ConnectionAccessor:
    """Wrapper to access Connection entries in template."""

    def __init__(self) -> None:
        self.var: Any = None

    def __getattr__(self, key: str) -> Any:
        from airflow.models.connection import Connection

        self.var = Connection.get_connection_from_secrets(key)
        return self.var

    def __repr__(self) -> str:
        return str(self.var)

    def get(self, key: str, default_conn: Any = None) -> Any:
        from airflow.exceptions import AirflowNotFoundException
        from airflow.models.connection import Connection

        try:
            return Connection.get_connection_from_secrets(key)
        except AirflowNotFoundException:
            return default_conn


def _create_deprecation_warning(key: str, replacements: List[str]) -> DeprecationWarning:
    message = f"Accessing {key!r} from the template is deprecated and will be removed in a future version."
    if not replacements:
        return DeprecationWarning(message)
    display_except_last = ", ".join(repr(r) for r in replacements[:-1])
    if display_except_last:
        message += f" Please use {display_except_last} or {replacements[-1]!r} instead."
    else:
        message += f" Please use {replacements[-1]!r} instead."
    return DeprecationWarning(message)


class Context(MutableMapping[str, Any]):
    """Jinja2 template context for task rendering.

    This is a mapping (dict-like) class that can lazily emit warnings when
    (and only when) deprecated context keys are accessed.
    """

    _DEPRECATION_REPLACEMENTS: Dict[str, List[str]] = {
        "execution_date": ["data_interval_start", "logical_date"],
        "next_ds": ["{{ data_interval_end | ds }}"],
        "next_ds_nodash": ["{{ data_interval_end | ds_nodash }}"],
        "next_execution_date": ["data_interval_end"],
        "prev_ds": [],
        "prev_ds_nodash": [],
        "prev_execution_date": [],
        "prev_execution_date_success": ["prev_data_interval_start_success"],
        "tomorrow_ds": [],
        "tomorrow_ds_nodash": [],
        "yesterday_ds": [],
        "yesterday_ds_nodash": [],
    }

    def __init__(self, context: MutableMapping[str, Any]) -> None:
        self._context = context
        self._deprecation_replacements = self._DEPRECATION_REPLACEMENTS.copy()

    def __repr__(self) -> str:
        return repr(self._context)

    def __reduce_ex__(self, protocol: int) -> Tuple[Any, ...]:
        """Pickle the context as a dict.

        We are intentionally going through ``__getitem__`` in this function,
        instead of using ``items()``, to trigger deprecation warnings.
        """
        items = [(key, self[key]) for key in self._context]
        return dict, (items,)

    def __getitem__(self, key: str) -> Any:
        with contextlib.suppress(KeyError):
            warnings.warn(_create_deprecation_warning(key, self._deprecation_replacements[key]), stacklevel=2)
        with contextlib.suppress(KeyError):
            return self._context[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self._deprecation_replacements.pop(key, None)
        self._context[key] = value

    def __delitem__(self, key: str) -> None:
        self._deprecation_replacements.pop(key, None)
        del self._context[key]

    def __contains__(self, key: str) -> bool:
        return key in self._context

    def __iter__(self) -> Iterator[str]:
        return iter(self._context)

    def __len__(self) -> int:
        return len(self._context)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Context):
            return NotImplemented
        return self._context == other._context

    def __ne__(self, other: Any) -> bool:
        if not isinstance(other, Context):
            return NotImplemented
        return self._context != other._context

    def keys(self) -> Iterable[str]:
        return self._context.keys()

    def items(self) -> Iterable[Tuple[str, Any]]:
        return self._context.items()

    def values(self) -> Iterable[Any]:
        return self._context.values()

    def copy_only(self, keys: Container[str]) -> "Context[str, Any]":
        return type(self)({k: v for k, v in self._context.items() if k in keys})
