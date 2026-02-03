import os
import glob

# Try different path variations
paths_to_try = [
    r"C:\Users\Ryan\Documents\data\五大联赛数据\比赛数据\Premier-League\Arsenal\",
    "C:/Users/Ryan/Documents/data/五大联赛数据/比赛数据/Premier-League/Arsenal/",
]

for path in paths_to_try:
    print(f"Trying: {path}")
    if os.path.exists(path):
        print(f"Found: {path}")
        files = os.listdir(path)
        print(f"Files: {files}")
        break
    else:
        print(f"Not found")

# Also try to find matchlog files
print("\nSearching for matchlog files...")
for root, dirs, files in os.walk(r"C:\Users\Ryan\Documents\data"):
    for file in files:
        if "matchlog" in file.lower():
            print(f"Found: {os.path.join(root, file)}")
