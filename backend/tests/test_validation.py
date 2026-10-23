import io

import pandas as pd
import pytest
from test_api import H, c, make_csv, new, ready, up


@pytest.mark.parametrize('sensors', [['vibration', 'missing'], ['vibration', 'vibration']])
def test_invalid_sensor_mapping_is_rejected(sensors):
    s = new()
    mapping = up(s, make_csv()).json()['mapping']
    mapping['sensors'] = sensors
    for path in ('check', 'process'):
        response = c.post('/api/datasets/' + path, json=mapping, headers=H(s))
        assert response.status_code == 422
    assert not c.get('/api/state', headers=H(s)).json()['unlocked']


@pytest.mark.parametrize('bad', ['oops', '', '2'])
def test_invalid_failure_labels_do_not_become_healthy(bad):
    s = new()
    csv = make_csv().replace('60.0,0', '60.0,' + bad)
    mapping = up(s, csv).json()['mapping']
    mapping['failure'] = 'failure'
    response = c.post('/api/datasets/process', json=mapping, headers=H(s))
    assert response.status_code == 422


@pytest.mark.parametrize('reading', ['inf', '-inf', 'NaN'])
def test_no_finite_sensor_readings_cannot_unlock(reading):
    s = new()
    csv = 'timestamp,machine_id,vibration\n' + '\n'.join(
        f'2026-09-{i+1:02d},A,{reading}' for i in range(30))
    up(s, csv)
    mapping = {'timestamp': 'timestamp', 'id': 'machine_id', 'sensors': ['vibration']}
    response = c.post('/api/datasets/process', json=mapping, headers=H(s))
    assert response.status_code == 422


def test_only_whitespace_equipment_ids_rejected():
    s = new()
    csv = make_csv().replace(',A,', ',   ,').replace(',B,', ',   ,').replace(',C,', ',   ,')
    up(s, csv)
    response = c.post('/api/datasets/process', json={
        'timestamp': 'timestamp', 'id': 'machine_id', 'sensors': ['vibration']}, headers=H(s))
    assert response.status_code == 422


def test_duplicate_headers_rejected():
    response = up(new(), 'timestamp,machine_id,vibration,vibration\n2026-01-01,A,1,2')
    assert response.status_code == 400


def test_normalized_duplicate_headers_rejected():
    response = up(new(), 'timestamp,machine_id,vibration, vibration \n2026-01-01,A,1,2')
    assert response.status_code == 400


def test_failed_upload_invalidates_previous_pending_file():
    s = new()
    mapping = up(s, make_csv()).json()['mapping']
    assert up(s, 'bad', 'bad.txt').status_code == 400
    assert c.post('/api/datasets/process', json=mapping, headers=H(s)).status_code == 409


def test_too_few_clean_rows_rejected():
    s = new()
    csv = 'timestamp,machine_id,vibration\n' + '\n'.join(['2026-09-01,A,2'] * 25)
    up(s, csv)
    response = c.post('/api/datasets/process', json={
        'timestamp': 'timestamp', 'id': 'machine_id', 'sensors': ['vibration']}, headers=H(s))
    assert response.status_code == 422


def test_xlsx_upload_and_processing():
    s = new()
    stream = io.BytesIO()
    pd.read_csv(io.StringIO(make_csv())).to_excel(stream, index=False)
    response = c.post('/api/datasets', files={'file': ('readings.xlsx', stream.getvalue())}, headers=H(s))
    assert response.status_code == 200
    assert c.post('/api/datasets/process', json=response.json()['mapping'], headers=H(s)).status_code == 200
    assert c.get('/api/overview', headers=H(s)).json()['kpis']['equipment']['value'] == 3


def test_offset_timestamps_and_asset_ids_with_slashes():
    s = new()
    csv = make_csv().replace(',A,', ',Plant/Pump A,')
    csv = csv.replace('2026-09-01,', '2026-09-01T02:00:00+02:00,')
    ready(s, csv)
    response = c.get('/api/equipment/Plant%2FPump%20A', headers=H(s))
    assert response.status_code == 200
    assert response.json()['records'] == 30


@pytest.mark.parametrize('payload', [{'title': '   '}, {'title': 'Inspect', 'asset': 'unknown'}])
def test_invalid_workorder_inputs(payload):
    s = new()
    ready(s)
    assert c.post('/api/workorders', json=payload, headers=H(s)).status_code == 422


@pytest.mark.parametrize('payload', [{'due': 'not-a-date'}, {'status': ''}])
def test_invalid_workorder_updates(payload):
    s = new()
    ready(s)
    wid = c.post('/api/workorders', json={'title': 'Inspect A', 'asset': 'A'}, headers=H(s)).json()['id']
    assert c.patch(f'/api/workorders/{wid}', json=payload, headers=H(s)).status_code == 422


def test_every_business_endpoint_is_gated():
    s = new()
    for path in ('overview', 'equipment', 'equipment/A', 'alerts', 'maintenance/recommendations', 'workorders', 'model'):
        assert c.get('/api/' + path, headers=H(s)).status_code == 409
    for path, payload in [('workorders', {'title': 'Inspect'}), ('model/train', None)]:
        assert c.post('/api/' + path, json=payload, headers=H(s)).status_code == 409


def test_unsupervised_training_reports_no_accuracy():
    s = new()
    csv = '\n'.join(','.join(line.split(',')[:4]) for line in make_csv().splitlines())
    ready(s, csv)
    result = c.post('/api/model/train', headers=H(s))
    assert result.status_code == 200
    assert result.json()['metrics'] is None


def test_equal_timestamps_do_not_train_and_test_on_same_instant():
    s = new()
    csv = 'timestamp,machine_id,vibration\n' + '\n'.join(f'2026-09-01,A,{i}' for i in range(30))
    ready(s, csv)
    assert c.post('/api/model/train', headers=H(s)).status_code == 422


def test_mixed_missing_values_are_reported_without_inventing_readings():
    s = new()
    csv = make_csv().replace('2026-09-01,A,2.00', '2026-09-01,A,inf')
    mapping = up(s, csv).json()['mapping']
    quality = c.post('/api/datasets/check', json=mapping, headers=H(s)).json()
    assert quality['invalid_sensor_values'] == 1
    assert c.post('/api/datasets/process', json=mapping, headers=H(s)).status_code == 200
    sensor = c.get('/api/equipment/A', headers=H(s)).json()['sensors']['vibration']
    assert len(sensor['points']) == 29
    assert sensor['points'][-1]['v'] == 8.43


def test_invalid_timestamp_ratio_rejected():
    s = new()
    csv = make_csv().replace('2026-09-0', 'bad-0')
    csv = csv.replace('2026-09-1', 'bad-1')
    up(s, csv)
    response = c.post('/api/datasets/check', json={
        'timestamp':'timestamp', 'id':'machine_id', 'sensors':['vibration']}, headers=H(s))
    assert response.status_code == 422
    assert 'timestamps' in str(response.json())


def test_oversized_file_rejected(monkeypatch):
    monkeypatch.setenv('SENTINELOPS_MAX_MB', '0')
    assert up(new(), make_csv()).status_code == 413


def test_unscored_equipment_has_no_fabricated_health():
    s = new()
    csv = 'timestamp,machine_id,vibration\n' + '\n'.join(f'2026-09-{i+1:02d},Asset-{i},{i}' for i in range(30))
    ready(s, csv)
    assets = c.get('/api/equipment', headers=H(s)).json()
    assert all(asset['status'] == 'unscored' and asset['health'] is None for asset in assets)
    assert c.get('/api/alerts', headers=H(s)).json() == []


def test_failed_processing_preserves_active_model_and_workorders():
    s = new()
    ready(s, '\n'.join(','.join(line.split(',')[:4]) for line in make_csv().splitlines()))
    trained = c.post('/api/model/train', headers=H(s)).json()
    c.post('/api/workorders', json={'title':'Inspect A', 'asset':'A'}, headers=H(s))
    mapping = up(s, make_csv(), 'replacement.csv').json()['mapping']
    mapping['id'] = 'unknown'
    assert c.post('/api/datasets/process', json=mapping, headers=H(s)).status_code == 422
    assert c.get('/api/model', headers=H(s)).json()['version'] == trained['version']
    assert len(c.get('/api/workorders', headers=H(s)).json()) == 1
    assert c.get('/api/state', headers=H(s)).json()['dataset']['name'] == 'd.csv'


def test_workorder_cannot_be_updated_from_another_session():
    a, b = new(), new()
    ready(a)
    ready(b)
    wid = c.post('/api/workorders', json={'title':'Inspect A'}, headers=H(a)).json()['id']
    assert c.patch(f'/api/workorders/{wid}', json={'status':'Done'}, headers=H(b)).status_code == 404


def test_numeric_timestamps_are_not_silently_interpreted_as_nanoseconds():
    s = new()
    csv = 'timestamp,machine_id,vibration\n' + '\n'.join(f'{1727000000+i},A,{i}' for i in range(30))
    up(s, csv)
    response = c.post('/api/datasets/check', json={
        'timestamp':'timestamp', 'id':'machine_id', 'sensors':['vibration']}, headers=H(s))
    assert response.status_code == 422
