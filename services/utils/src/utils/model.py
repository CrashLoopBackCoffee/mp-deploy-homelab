import os
import pathlib

import pulumi as p
import pydantic


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


class EnvVarRef(ConfigBaseModel):
    envvar: str

    @property
    def value(self) -> p.Output[str]:
        return p.Output.secret(os.environ[self.envvar])


class CloudflareConfig(ConfigBaseModel):
    api_token: EnvVarRef
    zone: str = 'mpagel.de'
