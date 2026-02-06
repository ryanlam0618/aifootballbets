import os
import shutil

# 創建歸檔目錄
archive_dir = 'archive'
os.makedirs(archive_dir, exist_ok=True)
os.makedirs(f'{archive_dir}/data_processing', exist_ok=True)
os.makedirs(f'{archive_dir}/old_tests', exist_ok=True)
os.makedirs(f'{archive_dir}/legacy', exist_ok=True)

# 舊版數據處理腳本
old_data_files = [
    'data_integration.py',
    'data_integration_v2.py', 
    'data_integration_v3.py',
    'cleanup_data.py',
    'cleanup_data_v2.py',
    'cleanup_history_data.py',
    'create_clean_history.py',
    'integrate_excel_stats.py',
    'explore_paths.py'
]

# 根目錄測試文件
old_test_files = [
    'test_data.py',
    'test_temp.py',
    'debug_mc.py'
]

# 移動數據處理腳本
for f in old_data_files:
    if os.path.exists(f):
        shutil.move(f, f'{archive_dir}/data_processing/')
        print(f'-> {archive_dir}/data_processing/{f}')

# 移動測試文件
for f in old_test_files:
    if os.path.exists(f):
        shutil.move(f, f'{archive_dir}/old_tests/')
        print(f'-> {archive_dir}/old_tests/{f}')

print('\nDone!')
