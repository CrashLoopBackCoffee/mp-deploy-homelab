"""Utilities for multi-tenant instances of services."""

import pulumi as p

STANDARD_STACK_NAMES = ('prod', 'dev')


def split_stack_name() -> tuple[str, str]:
    """Return an instance specific suffic derived from the stack name.

    For stacks `prod` and `dev` the suffix is the empty string. For a stack `prod-myinst` it would
    be `-myinst`. Such a suffix can then be used to isolate global resources of a deployment like
    public hostnames or the service namespace.
    """
    stack_name = p.get_stack()
    for standard_stack_name in STANDARD_STACK_NAMES:
        if stack_name.startswith(standard_stack_name):
            return standard_stack_name, stack_name[len(standard_stack_name) :]

    raise NotImplementedError(f'Stack {stack_name!r} starts with a non-standard name.')
