============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- /Users/davidhona/dev/franklinwh-cloud-test/venv/bin/python3.14
cachedir: .pytest_cache
rootdir: /Users/davidhona/dev/franklinwh-cloud
configfile: pyproject.toml
plugins: anyio-4.12.1, respx-0.22.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 25 items

tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[1-1_0] PASSED [  4%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[1-1_1] PASSED [  8%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[time_of_use-1] PASSED [ 12%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[TIME_OF_USE-1] PASSED [ 16%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[tou-1] PASSED [ 20%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[tou_battery_import-1] PASSED [ 24%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[2-2_0] PASSED [ 28%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[2-2_1] PASSED [ 32%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[self_consumption-2] PASSED [ 36%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[self-2] PASSED [ 40%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[3-3_0] PASSED [ 44%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[3-3_1] PASSED [ 48%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[emergency_backup-3] PASSED [ 52%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_mode_legacy_mapping[backup-3] PASSED [ 56%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[CUSTOM-CUSTOM] PASSED [ 60%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[HOME-HOME] PASSED [ 64%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[STANDBY-STANDBY] PASSED [ 68%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[SELF-SELF] PASSED [ 72%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[SOLAR-SOLAR] PASSED [ 76%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[GRID_EXPORT-GRID_EXPORT] PASSED [ 80%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[GRID_CHARGE-GRID_CHARGE] PASSED [ 84%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[8-CHARGE_FROM_GRID0] PASSED [ 88%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[8-CHARGE_FROM_GRID1] PASSED [ 92%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[7-EXPORT_TO_GRID_PEAKONLY0] PASSED [ 96%]
tests/test_backward_compatibility.py::TestBackwardCompatibility::test_set_tou_schedule_legacy_mapping[7-EXPORT_TO_GRID_PEAKONLY1] PASSED [100%]

============================== 25 passed in 0.07s ==============================
