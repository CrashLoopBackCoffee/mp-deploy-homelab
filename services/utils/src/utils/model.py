import os

import pulumi as p
import pydantic


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
