# %%
from ast import literal_eval
import importlib

import inspect
import json
from pathlib import Path
from collections import defaultdict
import re
import sys
from typing import DefaultDict
import docstring_parser

from mne_nodes.pipeline.io import TypedJSONEncoder
from mne_nodes.gui.parameter import (
    ArrayGui,
    BoolGui,
    ColorGui,
    ComboGui,
    DataFrameGui,
    DictGui,
    DualTupleGui,
    FloatGui,
    CallableGui,
    IntGui,
    ListGui,
    PathGui,
    StringGui,
    SliceGui,
)

default_type_guis = {
    "int": IntGui,
    "float": FloatGui,
    "str": StringGui,
    "bool": BoolGui,
    "list": ListGui,
    "dict": DictGui,
    "tuple": DualTupleGui,
    "combo": ComboGui,
    "path-like": PathGui,
    "slice": SliceGui,
    "DataFrame": DataFrameGui,
    "array": ArrayGui,
    "array-like": ArrayGui,
    "array_like": ArrayGui,
    "ndarray": ArrayGui,
    "color": ColorGui,
    "callable": CallableGui,
}

# Container types recognized as arrays, derived from default_type_guis so both
# stay in sync, e.g. "array of int" or "ndarray of float"
array_container_types = tuple(
    name for name, gui in default_type_guis.items() if gui is ArrayGui
)

type_defaults = {
            "int": 0,
            "float": 0.0,
            "bool": False,
            "str": "",
            "list": [],
            "dict": {},
            "tuple": (0, 0),
            "combo": "",
            "checklist": [],
            "slider": 0.0,
            "path-like": "",
            "slice": slice(0, 1),
        }


def _strip_shape_annotations(text):
    """Remove "(of/with) shape (...)" segments from a type description.

    Docstrings often annotate array types with their shape, e.g.
    "array, shape (n_samples, n_channels)" or "array-like of shape ``(2,)``".
    Since the dimensions use free-form names (not just digits) and may be
    wrapped in nested/mismatched brackets or rst markup (backticks), a plain
    regex can't reliably match them; a leftover fragment like "n_channels)"
    would otherwise be split off as a bogus type later on. This scans the
    text and drops each such segment using bracket-depth tracking.
    """
    open_brackets = "([{"
    close_brackets = ")]}"
    result = []
    i = 0
    n = len(text)
    while i < n:
        m = re.match(r"(?:of|with)?\s*shape\s*", text[i:], re.IGNORECASE)
        if m:
            j = i + m.end()
            # Skip markup/quote characters surrounding the shape, e.g. ``(...)``
            while j < n and text[j] in "`'\"= ":
                j += 1
            if j < n and text[j] in open_brackets:
                depth = 0
                k = j
                while k < n:
                    if text[k] in open_brackets:
                        depth += 1
                    elif text[k] in close_brackets:
                        depth -= 1
                        if depth == 0:
                            k += 1
                            break
                    k += 1
                while k < n and text[k] in "`'\"":
                    k += 1
                i = k
                continue
        result.append(text[i])
        i += 1
    return "".join(result)


# %%
def parse_rst_functions(path):
    text = Path(path).read_text()

    module_pattern = re.compile(r"\.\.\s*currentmodule::\s*([\w\.]+)")
    auto_module_pattern = re.compile(r"\.\.\s*automodule::\s*([\w\.]+)")

    module = None
    functions = defaultdict(list)

    for line in text.splitlines():
        # Detect module
        m = module_pattern.match(line.strip())
        if m:
            module = m.group(1)
            continue

        m = auto_module_pattern.match(line.strip())
        if m:
            module = m.group(1)
            continue

        # Detect items
        if line.startswith("   "):  # indented entries 3 spaces
            name = line.strip()
            if not name[0].isalpha():
                continue
            functions[module].append(name)

    return dict(functions)


# Group functions by API category
mnedev_api_path = Path(__file__).resolve().parents[2] / "mne-python/doc/api"
if not mnedev_api_path.exists():
    print(f"{mnedev_api_path} does not exist!")
    sys.exit(1)
exclude_categories = [
    "connectivity",
    "creating_from_arrays",
    "logging",
    "misc",
    "python_reference",
    "realtime",
]
api_categories = {
    f.stem: f
    for f in Path(mnedev_api_path).glob("*.rst")
    if f.stem not in exclude_categories
}

objects = {}
for category, category_path in api_categories.items():
    objects[category] = parse_rst_functions(category_path)


def get_param_config(param, sig, obj_config):
    # Skip parameters that don't have a valid name (e.g. *args, **kwargs)
    if not param.arg_name[0].isalpha():  # type: ignore
        return
    if param.arg_name == "filename":
        pass
    type_name = param.type_name  # type: ignore
    # Filter (<type> of length <length>)
    type_name = re.sub(r"(\w+)\s*of\s*length\s*\d+", r"\1", type_name)
    # Strip shape annotations, e.g. "array, shape (n_samples, n_channels)"
    type_name = _strip_shape_annotations(type_name)
    types = type_name.split("|")
    # split or
    types = [item for sublist in types for item in sublist.split(" or ")]
    # split ,
    types = [item for sublist in types for item in sublist.split(",")]
    # Remove spaces
    types = [t.strip() for t in types]
    # Strip rst inline-code markup, e.g. "``'auto'``" -> "'auto'"
    types = [t.strip("`") for t in types]
    # Get instance of <class> and use lower case
    pattern = r"instance of ([\w\.]+)"
    for idx, t in enumerate(types):
        match = re.match(pattern, t)
        if match:
            instance_type = match.group(1).split(".")[-1]
            types[idx] = instance_type
    # Get containers, e.g. "list of int" -> "list" or "array of int" -> "array"
    array_dtypes = {}
    pattern = r"(\w+(?:-\w+)*)\s*of\s*(\w+)"
    for idx, t in enumerate(types):
        match = re.match(pattern, t)
        if match:
            container_type = match.group(1)
            contained_type = match.group(2)
            if (
                container_type in ["list", "tuple"]
                and contained_type in default_type_guis
            ):
                types[idx] = container_type
            elif container_type in array_container_types and (
                contained_type in default_type_guis
                or contained_type in ("int", "float")
            ):
                types[idx] = container_type
                if contained_type in ("int", "float"):
                    array_dtypes[container_type] = contained_type
    # Get default from inspection signature
    default = sig.parameters[param.arg_name].default  # type: ignore
    # Get "type (default ***)" pattern
    pattern = r"(\w+)\s*\(default\s*([\w'\.]+)\)"
    for idx, t in enumerate(types):
        match = re.match(pattern, t)
        if match:
            tp = match.group(1)
            types[idx] = tp
            # Only try getting default from string if not gotten from signature
            if default is inspect.Parameter.empty:
                default_str = match.group(2)
                if default_str.startswith("'") and default_str.endswith("'"):
                    default = default_str.strip("'")
                else:
                    try:
                        default = literal_eval(default_str)
                    except (ValueError, SyntaxError):
                        default = default_str
    # Remove empty strings
    types = [t for t in types if t != ""]
    # # Remove parentheses
    # types = [t.replace("(", "").replace(")", "") for t in types]
    if "None" in types:
        none_select = True
        types.remove("None")
    else:
        # If default is None, still enable none_select
        none_select = default is None
    # Get string options and remove them from types
    def _is_quoted(t):
        return (t.startswith("'") and t.endswith("'")) or (
            t.startswith('"') and t.endswith('"')
        )

    options = [t.strip("'\"") for t in types if _is_quoted(t)]
    types = [t for t in types if not _is_quoted(t)]
    if len(options) > 0:
        types.append("combo")
    # Missing types
    missing = [t for t in types if t not in default_type_guis]
    if len(types) == 0 or len(missing) > 0:
        # Add params with missing types or no Default as inputs
        for mis in missing:
            missing_types[mis].add(param.arg_name)  # type: ignore
        input_config = {  # type: ignore
            "accepted": param.arg_name,  # type: ignore
            "optional": none_select,
            "types": types,
        }
        obj_config["inputs"][param.arg_name] = input_config  # type: ignore
        return
    # get rid of empty default
    if default is inspect.Parameter.empty:
        default = type_defaults.get(types[0], None)
        none_select = default is None or none_select
    # Check default with type for sometimes mismatch between type description and types
    if default is not None and type(default).__name__ not in types:
        if isinstance(default, int) and "float" in types:
            default = float(default)
        elif isinstance(default, float) and "int" in types:
            if default.is_integer():
                default = int(default)
        elif isinstance(default, tuple) and "list" in types:
            default = list(default)
        elif isinstance(default, list) and "tuple" in types:
            default = tuple(default)
        elif isinstance(default, str) and "path-like" in types:
            pass  # Skip path-like since path-gui suffices
        else:
            types.append(type(default).__name__)
    # Functions/other callables aren't JSON serializable; store as their name
    if callable(default) and not isinstance(default, type):
        default = getattr(default, "__name__", repr(default))
    # If types is "str" and "combo", then remove "str" and keep "combo"
    if len(types) == 2 and "str" in types and "combo" in types:
        types.remove("str")
    # Regular parameters with known types
    param_config = {}
    if len(types) > 1:
        param_config.update({"types": types, "gui": "MultiTypeGui"})
        type_kwargs = {}
        if len(options) > 0:
            type_kwargs["combo"] = {"options": options}
        for arr_type, dtype in array_dtypes.items():
            if arr_type in types:
                type_kwargs[arr_type] = {"dtype": dtype}
        if type_kwargs:
            param_config["type_kwargs"] = type_kwargs
    else:
        param_config.update({"gui": default_type_guis[types[0]].__name__})
        if len(options) > 0:
            param_config["options"] = options
        if types[0] in array_dtypes:
            param_config["gui_kwargs"] = {"dtype": array_dtypes[types[0]]}

    param_config.update(
        {
            "default": default,
            "none_select": none_select,
            "description": param.description,  # type: ignore
        }
    )
    obj_config["parameters"][param.arg_name] = param_config  # type: ignore


def should_skip_object(doc):
    skip_phrases = [
        "Direct class instantiation is discouraged",
        "This class should usually not be instantiated directly",
        "This class should not be instantiated directly",
        "This class is generally not meant to be instantiated directly",
        "Direct class instantiation is not supported",
        "should be instantiated with",
    ]
    return any(d in str(doc.description) for d in skip_phrases)


def build_object_config(
    obj,
    *,
    plugin_name,
    category,
    sub_category,
    object_path,
    class_name=None,
):
    docstring = inspect.getdoc(obj)
    if not docstring:
        return None
    doc = docstring_parser.parse(docstring)
    obj_config = {
        "inputs": {},
        "parameters": {},
        "outputs": {},
        "target": "file",
        "category": category,
        "sub_category": sub_category,
        "description": doc.long_description
        if doc.long_description
        else doc.short_description,
        "object_path": object_path,
        "class_name": class_name,
    }
    try:
        sig = inspect.signature(obj)
    except ValueError:
        print(
            f"Could not get signature for {object_path} in module {plugin_name}. Skipping."
        )
        return None
    parameters = [i for i in doc.meta if "param" in i.args]
    # add lower class-name as input if class_name is not None
    if class_name is not None:
        lower_name = class_name.lower()
        input_config = {
            "accepted": lower_name,
            "optional": False,
            "types": [lower_name],
        }
        obj_config["inputs"][lower_name] = input_config
        # change sub-category
        obj_config["sub_category"] = ".".join([sub_category, lower_name]) if sub_category else lower_name
    for param in parameters:
        if "," in param.arg_name:  # type: ignore
            # If multiple parameters are described in one line, split them.
            param_names = [name.strip() for name in param.arg_name.split(",")]  # type: ignore
            for name in param_names:
                param_copy = docstring_parser.DocstringParam(
                    args=param.args,
                    is_optional=param.is_optional,  # type: ignore
                    default=param.default,  # type: ignore
                    arg_name=name,
                    type_name=param.type_name,  # type: ignore
                    description=param.description,
                )
                if name not in sig.parameters:
                    continue
                get_param_config(param_copy, sig, obj_config)
        else:
            if param.arg_name not in sig.parameters:  # type: ignore
                continue
            get_param_config(param, sig, obj_config)
    for ret in doc.many_returns:
        # Set output name to class name if it is an instance of the class
        if ret.return_name is None:
            continue
        if class_name is not None and any(x in ret.return_name.lower() for x in ["inst", "instance", "self"]):
            output_name = class_name.lower()
        else:
            output_name = ret.return_name
        return_config = {"accepted": output_name}  # type: ignore
        obj_config["outputs"][output_name] = return_config  # type: ignore
    return doc, obj_config


def iter_public_class_methods(cls):
    seen = set()
    for owner_cls in cls.__mro__:
        if owner_cls is object:
            continue
        # Only include methods declared on classes that belong to mne.
        if not owner_cls.__module__.startswith("mne"):
            continue
        for method_name, method_obj in owner_cls.__dict__.items():
            if method_name.startswith("_") or method_name in seen:
                continue
            if isinstance(method_obj, (staticmethod, classmethod)):
                method_obj = method_obj.__func__
            if inspect.isfunction(method_obj):
                seen.add(method_name)
                yield method_name, method_obj


# %% Generate config
config = {}
missing_types = DefaultDict(set)
for category, module_dict in objects.items():
    for plugin_name, obj_list in module_dict.items():
        m_split = plugin_name.split(".")
        if len(m_split) == 1 or m_split[-1] == category:
            sub_category = None
        else:
            sub_category = m_split[-1]
        for obj_item in obj_list:
            sub_modules = obj_item.split(".")[:-1]
            obj_name = obj_item.split(".")[-1]
            complete_plugin_name = ".".join([plugin_name] + sub_modules)
            module = importlib.import_module(complete_plugin_name)
            obj = getattr(module, obj_name)
            if not inspect.isfunction(obj) and not inspect.isclass(obj):
                print(
                    f"Skipping {obj_item} in module {complete_plugin_name} because it's not a function or class."
                )
                continue
            if obj_name == "write_events":
                pass
            obj_config_result = build_object_config(
                obj,
                plugin_name=complete_plugin_name,
                category=category,
                sub_category=sub_category,
                object_path=obj_name,
            )
            if obj_config_result is None:
                continue
            doc, obj_config = obj_config_result
            if should_skip_object(doc):
                print(
                    f"Skipping {obj_item} because direct instantiation is discouraged."
                )
            else:
                config[obj_name] = obj_config

            if inspect.isclass(obj):
                for method_name, method_obj in iter_public_class_methods(obj):
                    method_path = f"{obj_name}.{method_name}"
                    method_config_result = build_object_config(
                        method_obj,
                        plugin_name=complete_plugin_name,
                        category=category,
                        sub_category=sub_category,
                        object_path=method_path,
                        class_name=obj_name,
                    )
                    if method_config_result is None:
                        continue
                    _, method_config = method_config_result
                    config[method_path] = method_config

# Save config
config_path = Path(__file__).parent / "mne_functions_config.json"
with open(config_path, "w") as file:
    json.dump(config, file, indent=4, cls=TypedJSONEncoder)

# Sort dictionary keys on length of their lists
missing_types = dict(sorted(missing_types.items(), key=lambda item: len(item[1]), reverse=True))

# Save missing types
missing_path = Path(__file__).parent / "missing_types.json"
with open(missing_path, "w") as file:
    json.dump(missing_types, file, indent=4, cls=TypedJSONEncoder)
print(f"Scraped {len(config)} functions/classes from mne")
print(f"Config saved to {config_path}")
print(f"Missing types saved to {missing_path}")
