"""Security and correctness regressions, using synthetic data and temporary storage."""
import io
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, os.environ.get('TEST_SOURCE', str(Path(__file__).resolve().parents[1])))
import server
from pipeline import contract
from pipeline.audit import AuditLog
from pipeline.model import Predictor, IntegrityError


@pytest.fixture
def client(tmp_path, monkeypatch):
    stores = {k: str(tmp_path / k) for k in server.STORE}
    for p in stores.values():
        Path(p).mkdir()
    monkeypatch.setattr(server, 'STORE', stores)
    monkeypatch.setattr(server, 'audit_log', AuditLog(str(tmp_path / 'audit' / 'audit.jsonl')))
    monkeypatch.setattr(server, 'predictor', Predictor(str(Path(server.ROOT) / 'model')))
    monkeypatch.setitem(server.CONFIG, 'channel2_envelope', False)
    monkeypatch.setitem(server.app.config, 'TESTING', True)
    return server.app.test_client()


def identity(role='importer', scope='alpha', user='alice'):
    return {'X-Demo-Role': role, 'X-Demo-Scope': scope, 'X-Demo-User': user}


def upload(client, custom=None):
    raw = custom or client.get('/api/v1/demo/csv?n=3', headers=identity()).data
    r = client.post('/api/v1/imports/file', data={'purpose': 'prediction',
                    'file': (io.BytesIO(raw), 'synthetic.csv')}, headers=identity())
    assert r.status_code == 201
    return r.json


def mapped(client):
    up = upload(client)
    r = client.post(f"/api/v1/imports/{up['import_id']}/mappings",
                    json={'mapping': up['proposed_mapping']['mapping']}, headers=identity('reviewer'))
    assert r.status_code == 200
    return up, r.json


@pytest.mark.parametrize('operation', ['mappings', 'confirm'])
def test_cross_scope_write_denied(client, operation):
    up, mp = mapped(client)
    r = client.post(f"/api/v1/imports/{up['import_id']}/{operation}",
                    json={'mapping': up['proposed_mapping']['mapping']},
                    headers=identity('reviewer', 'beta', 'bob'))
    assert r.status_code == 403


def test_cross_scope_cancel_denied(client):
    up = upload(client)
    server._save('runs', 'run-test', {'run_id': 'run-test', 'import_id': up['import_id'],
                                     'status': 'RUNNING'})
    r = client.post('/api/v1/runs/run-test/cancel', headers=identity('runner', 'beta', 'bob'))
    assert r.status_code == 403


def test_cross_scope_export_download_denied(client):
    up = upload(client)
    server._save('runs', 'run-test', {'run_id': 'run-test', 'import_id': up['import_id']})
    p = Path(server.STORE['exports']) / 'result.csv'
    p.write_text('RESEARCH_ONLY\n', encoding='utf-8')
    p.with_suffix('.csv.meta.json').write_text(json.dumps({'run_id': 'run-test'}), encoding='utf-8')
    r = client.get('/api/v1/exports/download?name=result.csv', headers=identity('viewer', 'beta', 'bob'))
    assert r.status_code == 403


def test_mapping_cannot_reference_another_import(client):
    up, mp = mapped(client)
    second = upload(client)
    r = client.post(f"/api/v1/imports/{second['import_id']}/confirm",
                    json={'mapping_version': mp['mapping_version']}, headers=identity('reviewer'))
    assert r.status_code == 400


def test_mapping_version_cannot_escape_store(client, tmp_path):
    up = upload(client)
    r = client.post(f"/api/v1/imports/{up['import_id']}/mappings",
                    json={'mapping': up['proposed_mapping']['mapping'], 'mapping_version': '../escaped'},
                    headers=identity('reviewer'))
    assert r.status_code == 400
    assert not (tmp_path / 'escaped.json').exists()


def test_mapping_updates_validation_for_custom_headers(client):
    raw = client.get('/api/v1/demo/csv?n=3', headers=identity()).data
    raw = raw.replace(b'age_at_onset', b'custom_onset_age', 1)
    up = upload(client, raw)
    mapping = up['proposed_mapping']['mapping']
    mapping['custom_onset_age'] = 'age_at_onset'
    r = client.post(f"/api/v1/imports/{up['import_id']}/mappings", json={'mapping': mapping},
                    headers=identity('reviewer'))
    assert r.status_code == 200
    r = client.post(f"/api/v1/imports/{up['import_id']}/confirm", json={}, headers=identity('reviewer'))
    assert r.status_code == 200
    assert r.json['runnable_rows'] == 3


def test_forbidden_columns_cannot_be_confirmed(client):
    raw = client.get('/api/v1/demo/csv?n=3', headers=identity()).data.decode('utf-8-sig')
    rows = raw.splitlines()
    raw = ('\n'.join([rows[0] + ',patient_name'] + [r + ',SYNTHETIC' for r in rows[1:]])).encode()
    up = upload(client, raw)
    client.post(f"/api/v1/imports/{up['import_id']}/mappings",
                json={'mapping': up['proposed_mapping']['mapping']}, headers=identity('reviewer'))
    r = client.post(f"/api/v1/imports/{up['import_id']}/confirm", json={}, headers=identity('reviewer'))
    assert r.status_code == 400


def test_confirmed_mapping_is_immutable(client):
    up, mp = mapped(client)
    assert client.post(f"/api/v1/imports/{up['import_id']}/confirm", json={},
                       headers=identity('reviewer')).status_code == 200
    r = client.post(f"/api/v1/imports/{up['import_id']}/mappings",
                    json={'mapping': up['proposed_mapping']['mapping']}, headers=identity('reviewer'))
    assert r.status_code == 409


def test_idempotency_key_does_not_leak_other_scope_run(client, monkeypatch):
    up, mp = mapped(client)
    client.post(f"/api/v1/imports/{up['import_id']}/confirm", json={}, headers=identity('reviewer'))
    server._save('runs', 'run-private', {'run_id': 'run-private', 'import_id': 'other',
        'created_by': 'bob', 'scope': 'beta', 'idempotency_key': 'shared'})
    monkeypatch.setattr(server.threading.Thread, 'start', lambda self: None)
    r = client.post('/api/v1/runs', json={'import_id': up['import_id']},
                    headers={**identity('runner'), 'Idempotency-Key': 'shared'})
    assert r.status_code == 202
    assert r.json['run_id'] != 'run-private'


def test_duplicate_ids_do_not_enter_model(client):
    raw = client.get('/api/v1/demo/csv?n=1', headers=identity()).data
    lines = raw.decode('utf-8-sig').splitlines()
    raw = ('\n'.join([lines[0], lines[1], lines[1]])).encode()
    cols, rows, enc, errs = contract.parse_raw(raw)
    validation = contract.validate(cols, rows, 'forward', enc, errs)
    cleaned = contract.clean_records(cols, rows, 'forward', {k: k for k in cols})
    assert validation.runnable_rows == len(cleaned) == 1


def test_empty_checksum_manifest_rejected(tmp_path):
    model = Path(server.ROOT) / 'model'
    for p in model.iterdir():
        shutil.copy2(p, tmp_path / p.name)
    (tmp_path / 'SHA256SUMS').write_text('')
    with pytest.raises(IntegrityError):
        Predictor(str(tmp_path))


def test_malformed_csv_is_rejected_without_server_error(client):
    up = upload(client, b'case_id\n' + b'a' * 150000)
    assert up['stage'] == 'FAILED'
    assert 'E501' in up['validation']['codes_seen']


def test_duplicate_csv_headers_rejected(client):
    cols, rows, enc, errs = contract.parse_raw(b'case_id,case_id\naaaaaa,bbbbbb\n')
    assert errs and errs[0].code == 'E103'


def test_concurrent_read_write_never_exposes_partial_or_locked_file(client):
    server._save('runs', 'run-concurrent', {'value': 0})
    def worker(index):
        for n in range(50):
            server._save('runs', 'run-concurrent', {'value': index * 50 + n})
            assert isinstance(server._load('runs', 'run-concurrent')['value'], int)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, range(4)))


@pytest.mark.parametrize('path', ['/api/v1/demo/csv?scenario=reverse&n=3', '/api/v1/templates/reverse'])
def test_reverse_csv_is_valid_and_headers_are_unique(client, path):
    cols, rows, enc, errs = contract.parse_raw(client.get(path).data)
    assert len(cols) == len(set(cols))
    result = contract.validate(cols, rows, 'reverse', enc, errs)
    assert result.ok
    assert not result.forbidden_hits


def test_cancel_during_inference_does_not_publish_results(client, monkeypatch):
    up, mp = mapped(client)
    client.post(f"/api/v1/imports/{up['import_id']}/confirm", json={}, headers=identity('reviewer'))
    monkeypatch.setattr(server.threading.Thread, 'start', lambda self: None)
    r = client.post('/api/v1/runs', json={'import_id': up['import_id']}, headers=identity('runner'))
    rid = r.json['run_id']
    original = server._call_boundary
    def cancel_then_infer(payload):
        response = client.post(f'/api/v1/runs/{rid}/cancel', headers=identity('runner'))
        assert response.status_code == 200
        return original(payload)
    monkeypatch.setattr(server, '_call_boundary', cancel_then_infer)
    server._execute_run(rid)
    assert server._load('runs', rid)['status'] == 'CANCELLED'
    assert server._load('results', rid) is None


def test_reverse_grid_stays_within_training_support(client):
    row = {'management': {'case_id': '0a1b2c3d4e5f6789'},
           'features': {'epilepsy_duration_before_remission_years': 6.2, 'seizure_free_months': 27,
            'age_at_onset': 9, 'febrile_seizure_history': 0, 'seizure_count_before_remission': 4,
            'self_limiting_syndrome': 0, 'developmental_delay': 0, 'eeg_epileptiform': 1},
           'extension': {'relative_dose_reduction_pct': 20},
           'reverse': {'planned_reduction_pct': 20, 'current_daily_dose_mg': 1000}}
    out = server.predictor.reverse_rows([row], 1.0)[0]
    low, high = server.predictor.support['relative_dose_reduction_pct']
    assert low <= out['feasible_reduction_range']['pct_low']
    assert out['feasible_reduction_range']['pct_upper'] <= high


@pytest.mark.parametrize('body', [[], ['bad'], {'scenario': 'unknown', 'fields': {'case_id': 'abc'}},
                                      {'scenario': 'reverse', 'target_risk': 'bad', 'fields': {'case_id': 'abc'}}])
def test_invalid_prediction_inputs_return_client_error(client, body):
    r = client.post('/api/v1/predictions', json=body, headers=identity())
    assert 400 <= r.status_code < 500


def test_single_explanation_reconstructs_risk_and_refuses_out_of_support(client):
    fields = {
        "case_id": "0a1b2c3d4e5f6789", "index_date": date.today().isoformat(),
        "epilepsy_duration_before_remission_years": 6.2, "seizure_free_months": 27,
        "age_at_onset": 9, "febrile_seizure_history": 0, "seizure_count_before_remission": 4,
        "self_limiting_syndrome": 0, "developmental_delay": 0, "eeg_epileptiform": 1,
    }
    response = client.post("/api/v1/predictions", json={"fields": fields}, headers=identity())
    assert response.status_code == 200
    result = response.json
    risk = result["risk_730d"]
    assert result["status"] == "OK"
    assert result["risk_730"] == risk
    assert result["threshold_basis"] == "demo_only"
    assert result["risk_curve"] == [{"t": 730, "risk": risk}]
    assert result["ci"] is None
    directions = {"+": 1, "-": -1, "0": 0}
    features = result["top_features"]
    assert {item["feature"] for item in features} == set(server.predictor.features)
    reconstructed = result["baseline_risk"] + sum(
        directions[item["direction"]] * item["impact"] for item in features)
    assert reconstructed == pytest.approx(risk, abs=0.00000051)
    assert len(result["global_features"]) == 5

    fields["age_at_onset"] = 100
    rejected = client.post("/api/v1/predictions", json={"fields": fields}, headers=identity()).json
    assert rejected["status"] == "REJECTED"
    assert rejected["risk_730d"] is None
    assert "top_features" not in rejected and "risk_curve" not in rejected
