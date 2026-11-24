/**
 * The review's schemas, for a finder's answer and the merging agent's groups, and where a JSON value breaks one, in
 * the words an agent fixes it from. It knows only what those schemas use, to need no validator as a dependency: type,
 * required, properties, additionalProperties, items, enum and minItems. A schema that uses anything else stops, rather
 * than passing values it can't check.
 */
import fs from 'node:fs';
import path from 'node:path';

import { ROOT } from '../src/root.ts';

// The schema lives with the pack-findings skill, so a local review and CI read one copy.
export const SCHEMA = path.join(ROOT, 'skills', 'pack-findings', 'findings.schema.json');

export interface Schema {
  readonly type?: 'object' | 'array' | 'string' | 'integer' | 'boolean';
  readonly required?: readonly string[];
  readonly properties?: Readonly<Record<string, Schema>>;
  readonly additionalProperties?: boolean;
  readonly items?: Schema;
  readonly enum?: readonly unknown[];
  readonly minItems?: number;
  readonly description?: string;
}

const KNOWN = new Set([
  'type',
  'required',
  'properties',
  'additionalProperties',
  'items',
  'enum',
  'minItems',
  'description',
]);
const ARTICLES = {
  object: 'an object',
  array: 'an array',
  string: 'a string',
  integer: 'an integer',
  boolean: 'true or false',
} as const;

function isType(value: unknown, kind: NonNullable<Schema['type']>): boolean {
  switch (kind) {
    case 'object':
      return value !== null && typeof value === 'object' && !Array.isArray(value);
    case 'array':
      return Array.isArray(value);
    case 'string':
      return typeof value === 'string';
    case 'integer':
      return Number.isInteger(value);
    case 'boolean':
      return typeof value === 'boolean';
  }
}

/** Stop when any part of schema uses a keyword errors() doesn't check, even a part no value reaches. */
export function supported(schema: Schema, where = 'the schema'): void {
  const unknown = Object.keys(schema)
    .filter((key) => !KNOWN.has(key))
    .sort();
  if (unknown.length) throw new Error(`${where} uses ${unknown.join(', ')}, which schema.ts can't check`);
  for (const [key, part] of Object.entries(schema.properties ?? {})) supported(part, `${where}.${key}`);
  if (schema.items) supported(schema.items, `${where}[]`);
}

/** Each way value breaks schema, as a line naming where: findings[0].spots[1].line, for one. */
export function errors(value: unknown, schema: Schema): string[] {
  supported(schema);
  return broken(value, schema, null);
}

/** Each way value breaks schema, below where: null for the top of the answer. */
function broken(value: unknown, schema: Schema, where: string | null): string[] {
  const named = where ?? 'the answer';
  if (schema.enum && !schema.enum.includes(value)) {
    return [`${named} must be one of ${schema.enum.map((option) => JSON.stringify(option)).join(', ')}`];
  }
  const kind = schema.type;
  if (kind && !isType(value, kind)) return [`${named} must be ${ARTICLES[kind]}`];
  const found: string[] = [];
  if (kind === 'object') {
    const object = value as Record<string, unknown>;
    const properties = schema.properties ?? {};
    found.push(
      ...(schema.required ?? []).filter((key) => !Object.hasOwn(object, key)).map((key) => `${named} needs ${key}`),
    );
    if (schema.additionalProperties === false) {
      found.push(
        ...Object.keys(object)
          .filter((key) => !Object.hasOwn(properties, key))
          .map((key) => `${named} has ${key}, which the schema has no place for`),
      );
    }
    for (const [key, part] of Object.entries(properties)) {
      if (Object.hasOwn(object, key)) found.push(...broken(object[key], part, where ? `${where}.${key}` : key));
    }
  }
  if (kind === 'array') {
    const array = value as unknown[];
    if (array.length < (schema.minItems ?? 0)) found.push(`${named} needs at least ${schema.minItems}`);
    for (const [n, item] of array.entries()) found.push(...broken(item, schema.items ?? {}, `${named}[${n}]`));
  }
  return found;
}

export function findingsSchema(): Schema {
  return JSON.parse(fs.readFileSync(SCHEMA, 'utf8'));
}

/**
 * The merging agent's answer: which of the finders' findings make each finding, with its kind, headline and take,
 * from the findings schema. A script builds the rest of each finding from its group's findings.
 */
export function groupsSchema(): Schema {
  const finding = findingsSchema().properties!.findings!.items!.properties!;
  const group: Schema = {
    type: 'object',
    additionalProperties: false,
    required: ['ids', 'kind', 'headline', 'take'],
    properties: {
      ids: {
        type: 'array',
        minItems: 1,
        items: { type: 'string' },
        description: "The ids of the finders' findings this one merges.",
      },
      kind: finding.kind!,
      headline: finding.headline!,
      take: finding.take!,
    },
  };
  return {
    type: 'object',
    additionalProperties: false,
    required: ['groups'],
    properties: { groups: { type: 'array', items: group } },
  };
}
