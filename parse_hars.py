import json
import glob

all_dispatches = {}

for file in glob.glob("hars/*.har"):
    try:
        with open(file) as f:
            data = json.load(f)
            
        for entry in data.get("log", {}).get("entries", []):
            url = entry.get("request", {}).get("url", "")
            if "getTouDispatchDetail" in url:
                try:
                    resp_text = entry.get("response", {}).get("content", {}).get("text", "{}")
                    resp = json.loads(resp_text)
                    dl = resp.get("result", {}).get("detailDefaultVo", {}).get("touDispatchList", [])
                    for item in dl:
                        id_val = item.get("id")
                        code = item.get("dispatchCode")
                        title = item.get("title")
                        if id_val not in all_dispatches:
                            all_dispatches[id_val] = {"code": code, "title": title}
                except Exception as e:
                    pass
    except Exception as e:
        pass

for k, v in sorted(all_dispatches.items()):
    print(f"ID={k}, code={v['code']}, title={v['title']}")
