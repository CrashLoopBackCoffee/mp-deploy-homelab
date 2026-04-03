import os
import pathlib

import pulumi as p
import pydantic
import pydantic_core.core_schema as pyd_core_schema


def get_pulumi_project(model_dir: str):
    search_dir = pathlib.Path(model_dir).parent

    while not (search_dir / 'Pulumi.yaml').exists():
        if not search_dir.parents:
            raise ValueError('Could not find repo root')

        search_dir = search_dir.parent
    return search_dir.parent.name


class ConfigBaseModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=lambda s: s.replace('_', '-'),
        populate_by_name=True,
        extra='forbid',
    )


class PulumiSecret(str):
    """Convenience class for Pulumi secrets.

    This makes it possible to accept pulumi secrets in the json schema
    while at the same time allowing the use of plain strings as pulumi decrypts the secrets
    before validating the model.

    Use like:
    ```python
    private_key: PulumiSecret
    ```
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        # Python validation: only accept strings (Pulumi already converted)
        return pyd_core_schema.str_schema()

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        # Override JSON schema to only allow secure object format
        return {
            'type': 'object',
            'properties': {'secure': {'type': 'string'}},
            'required': ['secure'],
            'additionalProperties': False,
            'description': 'Encrypted value.',
        }


class EnvVarRef(ConfigBaseModel):
    envvar: str

    @property
    def value(self) -> p.Output[str]:
        return p.Output.secret(os.environ[self.envvar])


class CloudflareConfig(ConfigBaseModel):
    api_token: EnvVarRef
    zone: str = 'mpagel.de'
