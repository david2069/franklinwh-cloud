# FranklinWH API Endpoints Mapping

A complete mapping of the internal `franklinwh-cloud` Python methods to their corresponding Cloud API HTTP endpoints.


## Account

| Python Method | Arguments | HTTP | Cloud API Endpoint | Cookbook Sample |
|---------------|-----------|------|--------------------|-----------------|
| `get_home_gateway_list()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_entrance_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_unread_count()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_notifications()` | `pageNum, pageSize` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_notification_settings()` | `lang` | GET | `/hes-gateway/terminal/selectEventClassification` | [View Examples](API_COOKBOOK.md) |
| `get_site_and_device_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_warranty_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_equipment_location()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_user_resources()` | — | GET | `/hes-gateway/newApi/api-user/app/resource/getUserResources/v2` | [View Examples](API_COOKBOOK.md) |
| `get_alarm_codes_list()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_programme_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_benefit_info()` | `data_type, day_time` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_gateway_alarm()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_grid_profile_info()` | `requestType` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_geography_list()` | `countryId` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_backup_history()` | `requestType, pageNum, pageSize` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `smart_assistant()` | `requestType, query` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_electric_data()` | `data_type, day_time` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_charge_history()` | `page_num, page_size` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `query_terminal_user_info()` | — | GET | `/hes-gateway/terminal/v2/queryTerminalUserInfo` | [View Examples](API_COOKBOOK.md) |
| `logout()` | `refresh_token` | POST | `/hes-gateway/terminal/v2/loginOut` | [View Examples](API_COOKBOOK.md) |
| `update_fcm_token()` | `token, identity, lang` | POST | `/hes-gateway/terminal/updateTerUserFcmToken` | [View Examples](API_COOKBOOK.md) |
| `get_messages_by_type()` | `event_types, page_num, page_size` | GET | `/hes-gateway/terminal/listDeviceMessagesByType` | [View Examples](API_COOKBOOK.md) |
| `get_run_log_list()` | `country_id` | GET | `/hes-gateway/common/country/selectRunLogList` | [View Examples](API_COOKBOOK.md) |

## Devices

| Python Method | Arguments | HTTP | Cloud API Endpoint | Cookbook Sample |
|---------------|-----------|------|--------------------|-----------------|
| `get_accessories()` | `option` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_power_cap_config_list()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_device_run_log_list()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_device_composite_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_agate_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_apower_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_device_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_span_settings()` | `requestType` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_span_setting()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_generator_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `set_generator_mode()` | `mode` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_site_detail()` | `site_id` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_device_detail()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_device_overall_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_system_settings()` | — | GET | `/hes-gateway/terminal/system/getSystemSetting` | [View Examples](API_COOKBOOK.md) |
| `update_system_settings()` | `is_pcs_dischg_en` | POST | `/hes-gateway/terminal/system/updateSystemSetting` | [View Examples](API_COOKBOOK.md) |
| `get_page_by_type_list()` | `type_list` | GET | `/hes-gateway/common/getPageByTypeList` | [View Examples](API_COOKBOOK.md) |

## Modes

| Python Method | Arguments | HTTP | Cloud API Endpoint | Cookbook Sample |
|---------------|-----------|------|--------------------|-----------------|
| `set_mode()` | `requestedOperatingMode, requestedSOC, reqbackupForeverFlag, reqnextWorkMode, reqdurationMinutes` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `update_soc()` | `requestedSOC, workMode, electricityType` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |

## Power

| Python Method | Arguments | HTTP | Cloud API Endpoint | Cookbook Sample |
|---------------|-----------|------|--------------------|-----------------|
| `set_grid_status()` | `status, soc` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_grid_status()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_power_control_settings()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `set_power_control_settings()` | `globalGridDischargeMax, globalGridChargeMax` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_pcs_hintinfo()` | `dispatchIdList` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |

## Stats

| Python Method | Arguments | HTTP | Cloud API Endpoint | Cookbook Sample |
|---------------|-----------|------|--------------------|-----------------|
| `get_runtime_data()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_power_by_day()` | `dayTime` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_power_details()` | `type, timeperiod` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |

## Storm

| Python Method | Arguments | HTTP | Cloud API Endpoint | Cookbook Sample |
|---------------|-----------|------|--------------------|-----------------|
| `get_storm_list()` | `pageNum, pageSize` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_progressing_storm_list()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_weather()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_storm_settings()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `set_storm_settings()` | `stormEn, setAdvanceBackupTime, advanceTime, stormNoticeEn` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |

## Tou

| Python Method | Arguments | HTTP | Cloud API Endpoint | Cookbook Sample |
|---------------|-----------|------|--------------------|-----------------|
| `get_gateway_tou_list()` | — | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_charge_power_details()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `save_tou_dispatch()` | `payload` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_tou_dispatch_detail()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_utility_companies()` | `country_id, province_id, page_num, page_size, latitude, longitude` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_tariff_list()` | `company_id, page_num, page_size, latitude, longitude, search_key` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_tariff_detail()` | `tariff_id` | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_tou_detail_by_id()` | `tou_id, from_type` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_custom_dispatch_list()` | `strategy_list` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_bonus_info()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_vpp_tip()` | — | GET | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `get_recommend_dispatch_list()` | `strategy_list` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `calculate_expected_earnings()` | `template` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `apply_tariff_template()` | `template_id, name, work_mode, electricity_type, strategy_detail_custom` | POST | `/{dynamic_url}` | [View Examples](API_COOKBOOK.md) |
| `check_ai_dispatch_invitation()` | — | GET | `/hes-gateway/terminal/aiDispatch/checkAiDispatchInvitation` | [View Examples](API_COOKBOOK.md) |
| `get_ai_offline_disable_flag()` | — | GET | `/hes-gateway/terminal/aiDispatch/getAiOfflineDisableFlag` | [View Examples](API_COOKBOOK.md) |
| `check_vpp_eligibility()` | — | GET | `/hes-gateway/terminal/checkUserVppEligibility` | [View Examples](API_COOKBOOK.md) |
| `query_compliance_capacity()` | — | GET | `/hes-gateway/terminal/ja12/queryComplianceCapacity` | [View Examples](API_COOKBOOK.md) |
| `notify_ai_cache()` | — | POST | `/hes-gateway/terminal/tou/notify/ai/cache` | [View Examples](API_COOKBOOK.md) |
| `get_nps_show_tip()` | — | POST | `/hes-gateway/terminal/nps/getNpsShowTip` | [View Examples](API_COOKBOOK.md) |
| `whether_popup()` | `popup_type` | GET | `/hes-gateway/terminal/feedback/whetherPopUp` | [View Examples](API_COOKBOOK.md) |
