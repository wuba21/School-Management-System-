"""
config package initialization.
Includes runtime patches for forward compatibility (e.g. Python 3.14+ copy changes).
"""

from copy import copy
import django.template.context as _django_context


def _compat_context_copy(self):
    """
    Python 3.14 changed super() semantics in copy operations, which breaks
    Django 4.2's Context.__copy__. This safe copy creates a clean clone
    without delegating through super().__copy__().
    """
    duplicate = self.__class__.__new__(self.__class__)
    duplicate.__dict__.update(self.__dict__)
    duplicate.dicts = self.dicts[:]
    duplicate.render_context = copy(self.render_context)
    return duplicate


_django_context.Context.__copy__ = _compat_context_copy
