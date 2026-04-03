---
name: add-service-schema-generation
description: 'Add schema generation support to service X in this repo. Use when asked to enable config schema generation for a service with Pulumi config, add StackConfig and PulumiConfigRoot wrappers, register tool.config-models in pyproject.toml, and identify any Pulumi YAML key mismatches that appear after schema activation.'
argument-hint: 'service name, for example: observability'
---

# Add Service Schema Generation

Use this skill when a service in this repository has a Pulumi stack and config model but is not yet wired into the shared schema generator.

## What This Does

- Extends the service model to expose a Pulumi-shaped root model for JSON schema generation.
- Registers the service in the top-level `tool.config-models` section.
- Validates the affected Python files.
- Optionally checks Pulumi stack YAML files for alias mismatches after the schema is enabled.

## Preconditions

- The service lives under `services/<service>/`.
- The service has a Pulumi project at `services/<service>/pulumi/` with `Pulumi.yaml`.
- The service exposes its model from `services/<service>/pulumi/<service>/model.py`.

## Procedure

1. Read `services/<service>/pulumi/<service>/model.py` and confirm the top-level config class name used by the service, typically `ComponentConfig`.
2. Update that model file to import `get_pulumi_project` from `utils.model`.
3. Add these wrapper models to the service model file:

   ```python
   class StackConfig(ConfigBaseModel):
      model_config = {
         'alias_generator': lambda field_name: f'{get_pulumi_project(__file__)}:{field_name}'
      }
      config: ComponentConfig


   class PulumiConfigRoot(ConfigBaseModel):
      config: StackConfig
   ```
4. Add this entry to `pyproject.toml`:

   ```toml
   [tool.config-models.<service>]
   root = "services/<service>/pulumi"
   model = "<service>.model:PulumiConfigRoot"
   ```
5. Validate the edited Python files for errors.
6. If requested, run the repo schema generator so `.config-schema.json` and `.vscode/settings.json` are refreshed.
7. If YAML diagnostics appear after generation, inspect the service's `Pulumi.*.yaml` files for snake_case keys that should be dashed because `ConfigBaseModel` converts underscores to dashes.

## Notes

- Keep changes minimal and consistent with the existing ingress, kubernetes, paperless, samba, and observability patterns.
- Do not change unrelated config semantics while enabling schema generation.
- If the model shape uses Pulumi secret objects in YAML but plain strings in Python, report that mismatch separately instead of changing it implicitly.
