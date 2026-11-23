"""Where a JSON value breaks a JSON Schema, in the words an agent fixes it from. It knows only what the review's own
schemas use, since the standard library has no validator: type, required, properties, additionalProperties, items,
enum and minItems. A schema that uses anything else stops, rather than passing values it can't check."""
import json

TYPES = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}
KNOWN = {'type', 'required', 'properties', 'additionalProperties', 'items', 'enum', 'minItems', 'description'}
ARTICLES = {'object': 'an object', 'array': 'an array', 'string': 'a string', 'integer': 'an integer',
            'boolean': 'true or false'}


def supported(schema, where='the schema'):
    """Stop when any part of schema uses a keyword errors() doesn't check, even a part no value reaches."""
    unknown = set(schema) - KNOWN
    if unknown:
        raise ValueError(f"{where} uses {', '.join(sorted(unknown))}, which schema.py can't check")
    for key, part in schema.get('properties', {}).items():
        supported(part, f'{where}.{key}')
    if 'items' in schema:
        supported(schema['items'], f'{where}[]')


def errors(value, schema):
    """Each way value breaks schema, as a line naming where: findings[0].spots[1].line, for one."""
    supported(schema)
    return broken(value, schema, None)


def broken(value, schema, where):
    """Each way value breaks schema, below where: None for the top of the answer."""
    named = where or 'the answer'
    if 'enum' in schema and value not in schema['enum']:
        return [f'{named} must be one of {", ".join(json.dumps(option) for option in schema["enum"])}']
    kind = schema.get('type')
    # A bool is an int in Python, but not an integer in JSON.
    if kind and (not isinstance(value, TYPES[kind]) or kind == 'integer' and isinstance(value, bool)):
        return [f'{named} must be {ARTICLES[kind]}']
    found = []
    if kind == 'object':
        properties = schema.get('properties', {})
        found += [f'{named} needs {key}' for key in schema.get('required', []) if key not in value]
        if schema.get('additionalProperties') is False:
            found += [f'{named} has {key}, which the schema has no place for' for key in value if key not in properties]
        for key, part in properties.items():
            if key in value:
                found += broken(value[key], part, f'{where}.{key}' if where else key)
    if kind == 'array':
        if len(value) < schema.get('minItems', 0):
            found.append(f'{named} needs at least {schema["minItems"]}')
        for n, item in enumerate(value):
            found += broken(item, schema.get('items', {}), f'{named}[{n}]')
    return found
