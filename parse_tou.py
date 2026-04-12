import json

with open("scratch_dispatch.json") as f:
    d = json.load(f)

res = d.get("result", {})
vo = res.get("detailDefaultVo", {})
dl = vo.get("touDispatchList", [])

print(f"Total defined dispatch rules: {len(dl)}")
for item in dl:
    print(f"ID={item.get('id')}, code={item.get('dispatchCode')}, title={item.get('title')}")
