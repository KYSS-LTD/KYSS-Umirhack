import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / 'agent'))
from diagnostics import check_cpu_advanced, check_disk_advanced, parse_task_params, truncate_text


def test_truncate_marks_overflow():
    value = 'x' * 9000
    out = truncate_text(value)
    assert len(out) <= 8000
    assert 'truncated' in out


def test_parse_task_params_from_json_command():
    task = {'command': '{"host":"example.com","ports":[80,443]}'}
    params = parse_task_params(task)
    assert params['host'] == 'example.com'
    assert params['ports'] == [80, 443]


def test_cpu_advanced_has_summary_and_metrics():
    payload = check_cpu_advanced({})
    assert payload['level'] in {'OK', 'WARN', 'CRIT'}
    assert 'load_avg' in payload['metrics']


def test_disk_advanced_structure():
    payload = check_disk_advanced({'warn_percent': 85})
    assert payload['level'] in {'OK', 'WARN', 'CRIT'}
    assert 'mounts' in payload['metrics']
