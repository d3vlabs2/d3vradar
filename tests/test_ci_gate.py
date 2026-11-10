import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('ci_gate', Path(__file__).parents[1]/'deploy/check_ci.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

def test_requires_exact_successful_main_push():
    good = dict(id=1, head_sha='abc', head_branch='main', event='push', status='completed', conclusion='success')
    assert gate.passed([good], 'abc')
    assert not gate.passed([good], 'other')
    for field, value in [('head_branch','feature'),('event','pull_request'),('status','in_progress'),('conclusion','failure')]:
        assert not gate.passed([{**good, field:value}], 'abc')
    assert not gate.passed([good,{**good,'id':2,'conclusion':'failure'}], 'abc')
    assert not gate.passed([], 'abc')
