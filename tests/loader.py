"""scripts/*.py 를 별칭 모듈로 로드한다(select.py 가 stdlib select 와 겹치는 문제 회피)."""
import importlib.util
import os

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")


def load(modname, filename):
    path = os.path.abspath(os.path.join(SCRIPTS, filename))
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
